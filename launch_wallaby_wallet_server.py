#!/usr/bin/env python3
"""Local Firefox GUI for Wallaby Wallet. Standard-library HTTP bridge only."""
from balance_store import BalanceStore
from wallet_names import source_suggestions
from ownership import saved_bitaroo_destinations
from ownership_workspace import save_workspace,restore_workspace
from datetime import datetime,timezone
from decimal import Decimal
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path,PurePosixPath
import secrets
import signal
import socket
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit,parse_qs
import webbrowser
from reporting import export_html,render_html,select_report_year
from report_store import ReportStore,signature as report_signature
from profile_archive import ProfileArchive,ProfileGate
from nodes import NodeRegistry,create_agent_server,DEFAULT_AGENT_PORT
from preferences import resource_id,FamilyStore,MISSING_OWNERSHIP,MissingOwnership,resolve_ownership
from address_book import shared_address_book
from fees import FeeService,FeeUnavailable
from diagnostic_log import DiagnosticLog
from version import LABEL
from node_bridge import NodeBridge
from node_chain import RegistryRPC,configure as configure_nodes
from descriptor_store import DescriptorStore
from node_wallets import NodeWalletLoader
from wallet_names import display_inventory,display_summary
from bitaroo_inputs import merge_saved_uploads
from family_inputs import account_slot,account_id,folder_slot,declarations
from matching_policy import matching_window, DEFAULT_WINDOW
from descriptor_snapshot import history_ready
from transaction_templates import TemplateStore,clean_diagram
from transaction_workflows import WorkflowStore
from builder_workspace import BuilderWorkspace,LOCK as BUILDER_LOCK
from transaction_builder import builder_catalog
from fee_planner import plan as estimate_fee_plan,live_coins

ROOT=Path(__file__).resolve().parent
SLOTS={'bitaroo':{'.pdf'},'bitaroo_history':{'.pdf'},'bitaroo_current':{'.pdf'},'exchanges':{'.ods'},
       'quotes':{'.csv'},'cpi':{'.csv'},'tax_context':{'.json'}}
MAX_FILE=256*1024*1024
MISSING_CGT='Complete a CGT run after confirming Ownership to view wallet balances.'

class Session:
    def __init__(self,root,preferences_path=None):
        self.root=Path(root).expanduser().resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.preferences_path=Path(preferences_path).expanduser().resolve() if preferences_path else self.root/'config.cfg'
        FamilyStore(self.preferences_path)
        self.current_page='';self.presence_seen=time.monotonic();self.presence_activity=self.presence_seen;self.presence_connected=False;self.token=secrets.token_urlsafe(32);self.lock=threading.RLock();self.events=[];self.pending=None
        self.status='idle';self.process=None;self.report=None;self.uploads={};self.settings={};self.last_job_error=None
        self.workspace_dirty=False;self.workspace_stamp=None;self.report_generation=None
        self.session_dir=self.root/('session-'+secrets.token_hex(8));self.session_dir.mkdir(mode=0o700)
        self.input_dir=self.session_dir/'inputs';self.input_dir.mkdir(mode=0o700)
        self.diagnostic_log=DiagnosticLog(self.preferences_path.parent/'logs');self.active_operations=0;self.rpc_broker=None;self.node_bridge=None;self.rpc_logged=set();self.node_load_cancel=threading.Event();self.node_registry=None;self.node_load_lock=threading.Lock();self.profile_gate=ProfileGate()
        self.transaction_refresh_context=None;self.transaction_refresh_scanned=False;self.ownership_completed_utc=None;self.descriptor_fingerprint=None;self.bitaroo_as_of_date=None;self.restore_error='';self.sequence=0;self.activity_started=False;self.closed=False;self.user_id=None;self.mode='cgt';self.job_result=None;self.inventory=[];self.inventory_ready=False;self.address_book=None;self.report=None;self.report_context=None;self.invalidate_transaction_refresh()
    def user(self):
        return FamilyStore(self.preferences_path).user(self.user_id) if self.user_id else None
    def sync_workspace(self,data):
        if not self.user_id or self.workspace_dirty or self.status in {'running','waiting'}:return
        meta=data.get('ownership_runs',{}).get(self.user_id)
        from statement_records import StatementRecords
        statement_records=StatementRecords(self.preferences_path)
        statement_revision=statement_records.read()['revision']
        stamp=(meta.get('data_id') if meta else None,meta.get('descriptor_fingerprint') if meta else None,statement_revision)
        if stamp==self.workspace_stamp:return
        self.inventory_ready=False;self.report=None;self.report_context=None;self.report_generation=None
        if not meta:
            statement_records.overlay(self.uploads,self.input_dir,data['users']);self.workspace_stamp=stamp;return
        try:
            restored=restore_workspace(self.preferences_path,self.user_id,self.input_dir)
            if restored:
                meta,self.uploads=restored;merge_saved_uploads(self.uploads,self.input_dir)
                self.inventory=meta['inventory'];self.inventory_ready=True;self.address_book=meta.get('address_book');self.settings=meta['settings']
                self.ownership_completed_utc=meta['completed_utc'];self.descriptor_fingerprint=meta.get('descriptor_fingerprint');self.bitaroo_as_of_date=meta.get('bitaroo_as_of_date');self.restore_error=''
                if 'bitaroo' in self.uploads:self.uploads[account_slot(self.user_id)]=self.uploads.pop('bitaroo')
                if not meta.get('family_accounts'):self.inventory_ready=False;self.restore_error='Run family-wide Ownership again to refresh the Bitaroo declarations.'
                statement_records.overlay(self.uploads,self.input_dir,data['users'])
                self.workspace_stamp=stamp
        except ValueError as error:self.restore_error=str(error)
    def access(self,snapshot=None):
        data=snapshot or FamilyStore(self.preferences_path).snapshot()
        user=next((u for u in data['users'] if u['id']==self.user_id),None)
        self.sync_workspace(data)
        descriptor_store=DescriptorStore(self.preferences_path)
        descriptors=descriptor_store.summary();ledger_ready=history_ready(self.preferences_path,None,fingerprint=descriptors['fingerprint'])
        assignment_required=__import__('ownership').needs_assignment(self.preferences_path,data,descriptors['wallets'],self.inventory) if user else False
        assignments_ready=False
        saved_inventory=data.get('ownership_runs',{}).get(self.user_id,{}).get('inventory',[])
        if user and (self.inventory or saved_inventory):
            inventory=[];current={resource_id('descriptor',w['id']) for w in descriptors['wallets']}
            from builder_identity import resolve
            for item in list(self.inventory or saved_inventory):
                item=dict(item)
                if item.get('kind')=='descriptor':
                    item['id']=resolve(self.preferences_path,item['id']);item['source']=json.loads(item['id'])[1]
                    if item['id'] not in current:continue
                if not any(r['id']==item['id'] for r in inventory):inventory.append(item)
            known={row['id'] for row in inventory}
            for wallet in descriptors['wallets']:
                rid=resource_id('descriptor',wallet['id'])
                if rid not in known:inventory.append({'id':rid,'kind':'descriptor','source':wallet['id'],'name':wallet['name']})
            try:resolve_ownership(data,inventory);assignments_ready=bool(inventory)
            except MissingOwnership:pass
        context=None
        if user and descriptors['ready'] and ledger_ready and self.descriptor_fingerprint==descriptors['fingerprint'] and self.inventory_ready and self.inventory:
            try:
                resolved=resolve_ownership(data,self.inventory)
                fields=('id','kind','source','name','owner_id','external','smsf','confirmed')
                rows=[{k:resolved[key].get(k) for k in fields} for key in sorted(resolved)]
                context=hashlib.sha256(json.dumps([user['id'],user['name'],rows,saved_bitaroo_destinations(data)],sort_keys=True,ensure_ascii=True).encode()).hexdigest()
            except MissingOwnership:pass
        if context is not None:
            try:declarations(data['users'],self.settings,self.uploads);declarations(data['users'],self.settings,self.uploads,smsf=True)
            except ValueError:context=None
        ready=context is not None
        saved_balance=BalanceStore(self.preferences_path).latest() if user else None
        balance_current=bool(ready and saved_balance and saved_balance.get('signature')==report_signature(data,descriptors['fingerprint']))
        from current_balances import needs_verification
        balance_refresh_required=ready and needs_verification(saved_balance,report_signature(data,descriptors['fingerprint']),data)
        node_ready=bool(self.node_registry and self.node_registry.ready_for_builders())
        available=ready or bool(saved_balance) or bool(assignments_ready and saved_inventory)
        if available and self.status not in {'running','waiting'}:
            generation,saved=ReportStore(self.preferences_path).load(self.user_id,report_signature(data,descriptors['fingerprint']),self.report_generation if self.report_context==context and self.report else None,allow_saved=True)
            if isinstance(saved,dict):self.report=saved;self.report_context=context
            elif saved is None:self.report=None;self.report_context=None
            self.report_generation=generation
        report_ready=available and self.report is not None
        return {'login_page':'ownership' if assignment_required else 'balances','ownership_assignment_required':assignment_required,'ownership_available':available,'balances_available':bool(saved_balance),'saved_data':bool(available and (not balance_current or not node_ready)), 'descriptor_history_ready':ledger_ready,'address_revision':__import__('address_destinations').AddressDestinations(self.preferences_path).revision(),'discovery_revision':descriptors['revision'],'node_ready':node_ready,'balances_ready':balance_current,'balance_refresh_required':bool(balance_refresh_required),'descriptors_ready':descriptors['ready'],'bitaroo_as_of_date':self.bitaroo_as_of_date,'ownership_completed_utc':self.ownership_completed_utc,'activity_started':bool(user) and self.activity_started,'process_active':bool(user) and (self.status in {'running','waiting'} or self.active_operations>0 or self.rpc_broker is not None and self.rpc_broker.pending(self.session_dir.name+':'+self.user_id)),'ownership_assignments_ready':assignments_ready,'builder_history_refreshing':assignments_ready and not ready,'ownership_ready':ready,'templates_ready':assignments_ready,'report_ready':report_ready,'report_generation':self.report_generation,'ownership_context':context}
    def invalidate_transaction_refresh(self):
        self.transaction_refresh_context=None;self.transaction_refresh_scanned=False
    def confirm_transaction_refresh(self):
        if self.access()['ownership_ready']:
            self.transaction_refresh_context=self.access()['ownership_context']
            
    def family(self):
        data=FamilyStore(self.preferences_path).snapshot()
        if not self.user_id:return {'users':[{k:v for k,v in u.items() if k in ('id','name','colour','gender')} for u in data['users']],'revision':data['revision'],'user':None,'ownership':[],'descriptors':{'wallets':[]},'builders':{},'password_authentication':True}
        access=self.access(data);user=next((u for u in data['users'] if u['id']==self.user_id),None)
        active=WorkflowStore(self.preferences_path).active(self.user_id) if user else []
        latest=max(active,key=lambda row:row['created_utc'])['id'] if active else None
        balance_report=BalanceStore(self.preferences_path).personal(report_signature(data,DescriptorStore(self.preferences_path).summary()['fingerprint']),user,allow_saved=True) if user and access['ownership_available'] else None
        from wallet_views import annotate_signers
        annotate_signers(balance_report,self.node_registry.hub if self.node_registry else None)
        from live_wallet_traits import annotate
        traits=annotate(balance_report,DescriptorStore(self.preferences_path).read(),self.node_registry)
        from live_wallet_traits import disc_flags
        discs=disc_flags(DescriptorStore(self.preferences_path).read(),self.node_registry)
        from archive_queue import ArchiveQueue
        archive=ArchiveQueue(self.node_registry.hub) if self.node_registry else None
        if balance_report and archive:
            for row in balance_report.get('balances',{}).get('wallets',[]):
                resource=resource_id('descriptor',row['descriptor_id']) if row.get('descriptor_id') else ''
                row['archive_sources']=[{k:v for k,v in item.items() if k not in ('public_wallet','related_policies')} for item in archive.options(resource)]
        from balance_evidence import annotate as balance_evidence
        balance_evidence(balance_report,DescriptorStore(self.preferences_path).read(),data,self.preferences_path)
        result={'known_vaults':self.node_registry.vaults.known() if self.node_registry and user else [],'rename_queue':__import__('wallet_renames').RenameQueue(self.node_registry.hub).snapshot() if self.node_registry and user else {'operations':[]},'archive_queue':archive.snapshot() if archive else {'requests':[]},'wallet_disc_traits':discs,'wallet_traits':traits,'builders':{kind:BuilderWorkspace(self.preferences_path).snapshot(self.user_id,kind,self.node_registry) for kind in ('wallet','transaction')} if user else {},'wallet_restorations':__import__('wallet_lifecycle').restoration_status(self.node_registry.hub,self.user_id) if self.node_registry and user else [],'balance_report':balance_report,'last_job_error':self.last_job_error,'active_transaction':latest,'users':data['users'],'revision':data['revision'],'ownership':[dict(r,name=__import__('wallet_names').dashboard_name(r)) for r in data['ownership']],'user':user,
                'descriptors':dict(display_summary(DescriptorStore(self.preferences_path).summary(),data),ready=access['descriptors_ready']),'inventory':[dict(item,**source_suggestions(item,data['users'])) for item in display_inventory(self.inventory,DescriptorStore(self.preferences_path).read())] if user else [],'inventory_ready':self.inventory_ready if user else False,
                **access,'address_book':__import__('address_destinations').AddressDestinations(self.preferences_path).overlay(shared_address_book(data,self.address_book or data.get('ownership_runs',{}).get(self.user_id,{}).get('address_book'))) if access['ownership_available'] else None,
                'restore_error':self.restore_error,'settings':self.settings if user else {},'loaded_slots':{slot:([p.name for p in sorted(path.rglob('*')) if p.is_file()] if path.is_dir() else [path.name]) for slot,path in self.uploads.items()} if user else {}}
        for row in result['inventory']:
            if row.get('source') in traits:row['watch_only']=traits[row['source']]
            row['disc_only']=discs.get(row.get('source'),False)
        for row in result['descriptors']['wallets']:
            if row['id'] in traits:row['watch_only']=traits[row['id']]
            row['disc_only']=discs.get(row['id'],False)
        return result
    def select_user(self,user_id):
        started=time.monotonic()
        with self.lock:
            if self.status in {'running','waiting'}:raise ValueError('Cancel the active job before switching users.')
            user=FamilyStore(self.preferences_path).user(user_id) if user_id else None
            if user_id and not user:raise ValueError('User no longer exists.')
            if self.node_registry:self.node_registry.hub.clear_lease(self)
            self.cancel();self.last_job_error=None;self.user_id=user_id;self.current_page='';self.presence_seen=time.monotonic();self.presence_activity=self.presence_seen;self.presence_connected=bool(user_id);self.report=None;self.job_result=None;self.events=[];self.pending=None;self.status='idle';self.sequence=0;self.activity_started=False;self.inventory=[];self.inventory_ready=False;self.address_book=None;self.report=None;self.report_context=None;self.invalidate_transaction_refresh()
            self.transaction_refresh_context=None;self.transaction_refresh_scanned=False;self.ownership_completed_utc=None;self.descriptor_fingerprint=None;self.bitaroo_as_of_date=None;self.restore_error='';self.uploads={};self.settings={};shutil.rmtree(self.input_dir,ignore_errors=True);self.input_dir.mkdir(parents=True,exist_ok=True)
            self.workspace_dirty=False;self.workspace_stamp=None;self.report_generation=None
            result=self.family()
            self.diagnostic_log.append('Browser','Login completed · elapsed_ms='+str(round((time.monotonic()-started)*1000))+' · saved_data='+str(result['saved_data']).lower())
            return result
    def close(self):
        with self.lock:
            if self.closed:return
            if self.node_registry:self.node_registry.hub.clear_lease(self)
            self.cancel();self.closed=True
            if self.process:
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
            if self.node_bridge:self.node_bridge.close();self.node_bridge=None
            shutil.rmtree(self.session_dir,ignore_errors=True)
    def emit(self,data):
        with self.lock:
            self.sequence+=1;event=dict(data,sequence=self.sequence);self.events.append(event)
            self.write_log(data)
            if data['type']=='prompt':self.pending=event;self.status='waiting'
            elif data['type']=='error':self.pending=None;self.status='error';self.last_job_error={'mode':self.mode,'message':str(data.get('message','The job stopped.'))}
            elif data['type']=='complete':self.pending=None;self.status='complete'
    def write_log(self,data):
        text=data.get('text') or data.get('message') or data.get('label') or data.get('prompt') or data['type']
        if data.get('context'):text=data['context']+'\n'+text
        user=self.user();self.diagnostic_log.append(user['name'] if user else 'Wallet Server',text)
    def record_activity(self,message,user_id=None):
        with self.lock:
            if self.closed or user_id is not None and self.user_id!=user_id:return
            self.activity_started=True
            self.emit({'type':'log','text':message})
    def upload(self,slot,name,body):
        if slot not in SLOTS and account_id(slot) is None:raise ValueError('Unknown input type')
        if account_id(slot) and not FamilyStore(self.preferences_path).user(account_id(slot)):raise ValueError('Unknown Bitaroo account user')
        path=PurePosixPath(name)
        if path.is_absolute() or not path.parts or any(p in {'..','.'} for p in path.parts) or '\\' in name or '\x00' in name:raise ValueError('Invalid input filename')
        if path.suffix.lower() not in SLOTS.get(slot,{'.pdf'}):raise ValueError('This file type does not belong in this input')
        if not folder_slot(slot) and len(path.parts)!=1:raise ValueError('Select one input file')
        with self.lock:
            if self.closed:raise ValueError('This browser workspace is closed')
            if self.status in {'running','waiting'}:raise ValueError('Wait for the current calculation before changing inputs')
            dest=self.input_dir/slot/Path(*path.parts);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
            self.write_log({'type':'log','text':'Reading '+name})
            self.uploads[slot]=self.input_dir/slot if folder_slot(slot) else dest
            self.workspace_dirty=True;self.inventory_ready=False;self.address_book=None;self.report=None;self.report_context=None;self.invalidate_transaction_refresh()
        return {'name':name,'bytes':len(body)}
    def upload_statements(self,slot,files,zone):
        if slot!='bitaroo' and account_id(slot) is None:raise ValueError('Unknown Bitaroo input type')
        if account_id(slot) and not FamilyStore(self.preferences_path).user(account_id(slot)):raise ValueError('Unknown Bitaroo account user')
        from statement_records import StatementRecords
        import tax_core_v107 as core
        with self.lock:
            if self.closed or self.status in {'running','waiting'}:raise ValueError('Wait for the current calculation before changing inputs.')
            uid=account_id(slot) or self.user_id
            key=uid+(':smsf' if slot.startswith('bitaroo_smsf_') else '')
            result=StatementRecords(self.preferences_path).accept(core,key,files,self.uploads.get(slot),self.input_dir/slot,zone)
            self.uploads[slot]=self.input_dir/slot
            self.workspace_dirty=True;self.inventory_ready=False;self.address_book=None;self.report=None;self.report_context=None;self.invalidate_transaction_refresh()
            self.write_log({'type':'log','text':f"Accepted {result['files']} Bitaroo PDFs; {result['retained']} distinct statement files retained."})
            return result
    def clear_slot(self,slot):
        if slot not in SLOTS and account_id(slot) is None:raise ValueError('Unknown input type')
        if account_id(slot) and not FamilyStore(self.preferences_path).user(account_id(slot)):raise ValueError('Unknown Bitaroo account user')
        with self.lock:
            if self.closed:raise ValueError('This browser workspace is closed')
            if self.status in {'running','waiting'}:raise ValueError('Calculation is still active')
            if slot=='bitaroo' or account_id(slot):
                uid=account_id(slot) or self.user_id
                __import__('statement_records').StatementRecords(self.preferences_path).discard({uid+(':smsf' if slot.startswith('bitaroo_smsf_') else '')})
            shutil.rmtree(self.input_dir/slot,ignore_errors=True);self.uploads.pop(slot,None);self.workspace_dirty=True;self.inventory_ready=False;self.address_book=None;self.report=None;self.report_context=None;self.invalidate_transaction_refresh()
    def worker_nodes(self):
        if self.node_bridge is None:self.node_bridge=NodeBridge(self.node_registry,lambda:self.closed or self.status not in {'running','waiting'},priority=lambda:100 if self.mode in ('inventory','balances','descriptors') else 50)
        return self.node_bridge.settings()
    def start_descriptor_scan(self,preserve_events=False):
        with self.lock:
            if self.status in {'running','waiting'}:raise ValueError('Wait for the active run before scanning descriptors.')
            if self.node_registry:__import__('retired_catalog').prepare(self.preferences_path,self.node_registry.hub)
            ds=DescriptorStore(self.preferences_path)
            if not self.user() or not ds.summary()['ready']:raise ValueError('Wait for automatic node wallet discovery to complete.')
            self.workspace_dirty=True;self.invalidate_transaction_refresh()
            if not preserve_events:self.events=[]
            self.pending=None;self.activity_started=True;self.status='running';self.mode='descriptors';self.job_result=None
            self.report=None;self.report_context=None
            self.result_path=self.session_dir/'report.json';self.result_path.unlink(missing_ok=True)
            config={'mode':'descriptors','user':self.user(),'family_snapshot':FamilyStore(self.preferences_path).snapshot(),'descriptor_catalog':ds.read(),'settings':{},'paths':{},'preferences':str(self.preferences_path),'cache':str(self.root/'historical-cache.sqlite3'),'result':str(self.result_path)}
            config['node_rpc']=self.worker_nodes()
            path=self.session_dir/'run.json';path.write_text(json.dumps(config))
            try:
                self.process=subprocess.Popen([sys.executable,str(ROOT/'worker.py'),str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',env=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1'),cwd=self.session_dir)
            except OSError:
                self.status='error';raise
            threading.Thread(target=self.consume,args=(self.process,),daemon=True).start()
    def start(self,settings,mode='cgt'):
        with self.lock:
            if self.closed:raise ValueError('This browser workspace is closed')
            if self.status in {'running','waiting'}:raise ValueError('A calculation is already active')
            self.last_job_error=None
            user=self.user()
            if not user:raise ValueError('Select a family user first.')
            if mode not in ('cgt','inventory','balances'):raise ValueError('Unknown job type.')
            if self.node_registry:__import__('retired_catalog').prepare(self.preferences_path,self.node_registry.hub)
            snapshot=FamilyStore(self.preferences_path).snapshot()
            access=self.access(snapshot)
            if mode in ('cgt','balances') and not access['ownership_ready']:raise ValueError(MISSING_OWNERSHIP)
            if mode=='cgt' and not access['balances_ready']:raise ValueError('Verify Balances in Ownership before building a CGT report.')
            self.run_context=access['ownership_context']
            self.run_refresh=False
            descriptor_store=DescriptorStore(self.preferences_path)
            if not descriptor_store.summary()['ready']:raise ValueError('Wait for automatic public wallet discovery before reviewing ownership.')
            window=matching_window(settings.get('matching_window',DEFAULT_WINDOW))
            refresh=settings.get('refresh_descriptor_history',False)
            if not isinstance(refresh,bool):raise ValueError('Descriptor refresh must be Yes or No.')
            self.run_refresh=mode=='inventory' and refresh
            zone=settings.get('browser_timezone') or self.settings.get('browser_timezone') or 'UTC'
            merge_saved_uploads(self.uploads,self.input_dir)
            declarations(snapshot['users'],dict(self.settings,**settings),self.uploads)
            required=('exchanges',)
            if mode in ('cgt','balances'):required+=('chain',)
            for slot in required:
                if slot not in self.uploads:raise ValueError('Select the required files in Ownership first.')
            if mode=='inventory' and 'opening_losses_by_user' not in settings:
                settings=dict(settings,opening_losses_by_user={user['id']:settings.get('carried_losses','0')})
            if mode=='inventory':self.settings={k:v for k,v in settings.items() if k not in {'taxpayer','financial_year','mode','matching_window','refresh_descriptor_history'}}
            settings=dict(self.settings,financial_year=settings.get('financial_year',''),taxpayer=user['name'],matching_window=window['key'],refresh_descriptor_history=refresh,display_timezone=zone)
            self.events=[];self.pending=None;self.activity_started=True;self.status='running';self.mode=mode;self.job_result=None
            if mode=='cgt':self.report=None;self.report_context=None
            if mode=='inventory':self.invalidate_transaction_refresh()
            if mode=='cgt':
                self.run_signature=report_signature(snapshot,descriptor_store.summary()['fingerprint'])
                self.report_generation=ReportStore(self.preferences_path).begin(self.run_signature)
            self.result_path=self.session_dir/'report.json'
            self.result_path.unlink(missing_ok=True)
            if mode=='balances':self.run_signature=report_signature(snapshot,descriptor_store.summary()['fingerprint'])
            config={'mode':mode,'user':user,'family_snapshot':snapshot,'ownership_completed_utc':self.ownership_completed_utc,'bitaroo_as_of_date':self.bitaroo_as_of_date,'descriptor_catalog':descriptor_store.read(),'descriptor_fingerprint':descriptor_store.summary()['fingerprint'],'settings':settings,'paths':{k:str(v) for k,v in self.uploads.items()},
                    'preferences':str(self.preferences_path),'cache':str(self.root/'historical-cache.sqlite3'),'result':str(self.result_path)}
            config['node_rpc']=self.worker_nodes()
            config_path=self.session_dir/'run.json';config_path.write_text(json.dumps(config))
            env=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
            self.process=subprocess.Popen([sys.executable,str(ROOT/'worker.py'),str(config_path)],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',env=env,cwd=self.session_dir)
            threading.Thread(target=self.consume,args=(self.process,),daemon=True).start()
    def consume(self,process):
        for line in process.stdout:
            try:data=json.loads(line)
            except ValueError:data={'type':'log','text':line.rstrip()}
            if data.get('type')=='trace_evidence':
                if process is self.process and self.mode in ('balances','cgt'):
                    current=report_signature(FamilyStore(self.preferences_path).snapshot(),DescriptorStore(self.preferences_path).summary()['fingerprint'])
                    if current==self.run_signature:
                        try:BalanceStore(self.preferences_path).save_evidence(current,data['graph'],data.get('trace_answers',[]))
                        except Exception as exc:
                            with self.lock:self.emit({'type':'log','text':'Could not preserve incomplete trace evidence: '+str(exc)})
                continue
            if data.get('type')=='complete' and process is self.process and self.status!='cancelled':
                try:
                    completed=json.loads(self.result_path.read_text())
                    if self.mode=='inventory':
                        book=completed.get('address_book')
                        if book:
                            for entry in book['entries']:
                                if entry.get('kind')=='bitaroo':FamilyStore(self.preferences_path).save_bitaroo_address(entry['source'],entry,book['generated_utc'])
                        self.inventory=completed['inventory'];self.inventory_ready=True;self.address_book=book
                        chain_path=Path(completed['chain_path'])
                        if chain_path!=self.result_path.with_name('descriptor_history.json') or not chain_path.is_file():raise ValueError('The descriptor history scan did not complete.')
                        self.uploads['chain']=chain_path
                        chain=json.loads(chain_path.read_text());self.descriptor_fingerprint=chain['catalog_fingerprint'];self.bitaroo_as_of_date=completed['bitaroo_as_of_date']
                        if {'exchanges','chain'}.issubset(self.uploads):
                            for profile in FamilyStore(self.preferences_path).snapshot()['users']:
                                uid=profile['id'];coverage=completed.get('coverage_by_user',{}).get(uid,{})
                                saved=save_workspace(self.preferences_path,uid,self.uploads,self.inventory,book,self.settings,metadata={'descriptor_fingerprint':self.descriptor_fingerprint,'bitaroo_as_of_date':coverage.get('bitaroo_as_of_date'),'bitaroo_data':completed.get('bitaroo_data_by_user',{}).get(uid,{}),'bitaroo_smsf_data':completed.get('bitaroo_smsf_data_by_user',{}).get(uid,{}),'historical_balances':completed.get('historical_balances',{}),'family_accounts':completed.get('family_accounts',{})})
                            self.ownership_completed_utc=saved['completed_utc'];self.restore_error='';self.workspace_dirty=False;self.workspace_stamp=None
                            with FamilyStore(self.preferences_path).transaction() as family_data:
                                family_data['bitaroo_accounts']=completed.get('family_accounts',{})
                                for uid,active in family_data['bitaroo_accounts'].items():
                                    if not active:family_data.get('bitaroo_addresses',{}).pop(uid,None)
                        if self.run_refresh:
                            self.transaction_refresh_scanned=True;self.confirm_transaction_refresh()
                    self.job_result=completed
                    if self.mode=='cgt':
                        snapshot=FamilyStore(self.preferences_path).snapshot()
                        current=report_signa…12353 tokens truncated…d,'transaction')['operations']:raise ValueError('This transaction does not belong to the active builder.')
                    if path.endswith('/sign'):return self.json(queue_sign(hub,session,data.get('id'),data.get('wallet_id'),data.get('node_id'),data.get('signer_id')))
                    return self.json(queue_broadcast(hub,session,data.get('id'),data.get('node_id')))
                if path=='/api/transaction/disc-check':
                    if not session.user():raise ValueError('Select a family user first.')
                    work=BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')
                    job=WorkflowStore(session.preferences_path).job(session.user_id,data.get('id'))
                    if job['creator_id']!=session.user_id or job['id'] not in work['operations'] or job.get('cancelled') or job.get('completed'):raise ValueError('Choose the active transaction before checking its signers.')
                    return self.json(sessions.nodes.hub.disc_signers.ensure(job['id'],force=True))
                if path=='/api/nodes/inventory-refresh':
                    if not session.user():raise ValueError('Select a family user first.')
                    hub=sessions.nodes.hub
                    for connection in list(sessions.nodes.connections.values()):
                        if not sessions.nodes.rpc._unique(connection):continue
                        hub.inventory_times[connection['node_id']]=0
                        threading.Thread(target=hub.refresh_inventory,args=(connection['node_id'],connection['token']),kwargs={'requested':True},daemon=True).start()
                    return self.json({'queued':True})
                if path in ('/api/wallets/rename','/api/wallets/rename-cancel','/api/wallets/rename-route'):
                    if not session.user():raise ValueError('Select a family user first.')
                    queue=__import__('wallet_renames').RenameQueue(sessions.nodes.hub)
                    if path.endswith('rename-cancel'):return self.json(queue.cancel(session.user_id,data.get('id')))
                    if path.endswith('rename-route'):return self.json(queue.route_archive(session.user_id,data.get('id'),data.get('target'),data.get('node_id')))
                    return self.json(queue.rename(session.user_id,data.get('wallet_id'),data.get('filename'),data.get('dashboard_name')))
                if path=='/api/nodes/delete':
                    if not session.user():raise ValueError('Select a family user first.')
                    with BUILDER_LOCK:return self.json(__import__('node_removal').remove(sessions.nodes,data.get('node_id'),session.user_id,data.get('confirmed')))
                if path=='/api/wallets/archive-route':
                    if not session.user():raise ValueError('Select a family user first.')
                    return self.json(__import__('archive_queue').ArchiveQueue(sessions.nodes.hub).route(session.user_id,data.get('id'),data.get('node_id')))
                if path in ('/api/wallets/archive','/api/wallets/archive-cancel'):
                    if not session.user():raise ValueError('Select a family user first.')
                    queue=__import__('archive_queue').ArchiveQueue(sessions.nodes.hub)
                    if path.endswith('archive-cancel'):return self.json(queue.cancel(session.user_id,data.get('id')))
                    return self.json(queue.create(session.user_id,data.get('wallet_id'),data.get('sources')))
                if path=='/api/wallets/restore':
                    if not session.user():raise ValueError('Select a family user first.')
                    return self.json(__import__('wallet_lifecycle').request_restore(sessions.nodes.hub,session.user_id,data.get('request_hash'),data.get('confirmed')))
                if path=='/api/wallets/retirement-cancel':
                    if not session.user():raise ValueError('Select a family user first.')
                    from wallet_retirement import cancel
                    return self.json(cancel(sessions.nodes.hub,session.user_id,data.get('request_hash'),data.get('confirmed')))
                if path=='/api/wallets/retire':
                    from wallet_retirement import propose
                    return self.json(propose(sessions.nodes.hub,session,data.get('wallet_id'),data.get('node_id'),data.get('confirmed')))
                if path=='/api/nodes/transfers/refresh-reviews':
                    if not session.user():raise ValueError('Select a family user first.')
                    return self.json(sessions.nodes.hub.transfers.refresh_reviews(data.get('transfer_ids'),data.get('confirmed')))
                if path=='/api/nodes/transfers/retry':
                    if not session.user():raise ValueError('Select a family user first.')
                    return self.json(sessions.nodes.hub.transfers.retry(data.get('transfer_id'),data.get('confirmed')))
                if path=='/api/nodes/rpc':
                    if not session.user():raise ValueError('Select a family user first.')
                    if not isinstance(data,dict) or not {'node_id','method'}<=set(data) or set(data)-{'node_id','method','params','wallet','timeout_seconds'}:raise ValueError('Invalid node RPC request.')
                    queued=sessions.nodes.rpc.queue(data['node_id'],data['method'],data.get('params',[]),data.get('wallet'),data.get('timeout_seconds',30),session.session_dir.name+':'+session.user_id)
                    session.record_activity('Nodes: queued '+queued['method']+' ('+queued['id']+').',session.user_id)
                    return self.json(queued,202)
                if path=='/api/presence/leave':
                    session.presence_connected=False
                    return self.json({'ok':True})
                if path=='/api/messages/send':
                    if not session.user():raise ValueError('Select a family user first.')
                    return self.json(WorkflowStore(session.preferences_path).send_message(session.user_id,data.get('user_id'),data.get('text')))
                if path=='/api/login':raise ValueError('Use password authentication to log in.')
                if path=='/api/logout':
                    sessions.auth.release_login(session.token)
                    return self.json(session.select_user(None))
                if path=='/api/users/save':
                    store.save_user(data.get('name',''),data.get('colour','green'),data.get('id'),data.get('revision'),gender=data.get('gender'),date_of_birth=__import__('preferences').validate_birth_date(data.get('date_of_birth')));return self.json(session.family())
                if path in ('/api/users/delete','/api/config/reset'):
                    target=data.get('id')
                    if any(s.status in {'running','waiting'} and (path=='/api/config/reset' or s.user_id==target) for s in list(sessions.sessions.values())):raise ValueError('Cancel active jobs for affected users before deleting or resetting.')
                    if path=='/api/config/reset':store.reset(data.get('revision'))
                    else:
                        if any(w['owner_id']==target for w in BuilderWorkspace(session.preferences_path).read()['workspaces'].values()):raise ValueError('Finish or cancel this user’s active builders before deleting the profile.')
                        store.delete_user(target,data.get('revision'))
                    sessions.auth.prune_users({u['id'] for u in store.snapshot()['users']})
                    WorkflowStore(session.preferences_path).prune_users([u['id'] for u in store.snapshot()['users']])
                    if path=='/api/config/reset':DescriptorStore(session.preferences_path).path.unlink(missing_ok=True)
                    for s in list(sessions.sessions.values()):
                        if s.user_id and not s.user():s.select_user(None)
                    return self.json(session.family())
                if path=='/api/transaction/complete':
                    if not session.user():raise ValueError('Select a family user first.')
                    BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')
                    if data.get('id') not in BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')['operations']:raise ValueError('This transaction does not belong to the active builder.')
                    WorkflowStore(session.preferences_path).complete(session.user_id,data.get('id'))
                    BuilderWorkspace(session.preferences_path).finish(session.user_id,'transaction')
                    return self.json(session.family())
                if path in ('/api/templates/save','/api/templates/delete'):
                    current=BuilderWorkspace(session.preferences_path).read()['workspaces'].get('transaction')
                    if current:BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')
                    self.require_builder_node(session,ownership=True)
                    if not session.access()['templates_ready']:raise ValueError('Complete Ownership and save all assignments before using transaction templates.')
                    templates=TemplateStore(session.preferences_path)
                    if path.endswith('/save'):return self.json(templates.save(data))
                    templates.delete(data.get('id'),data.get('revision'));return self.json({'deleted':True})
                if path in ('/api/notifications/read','/api/notifications/delete'):
                    if not session.user():raise ValueError('Select a family user first.')
                    workflows=WorkflowStore(session.preferences_path)
                    if path.endswith('/delete') and str(data.get('id','')).startswith('node-conflict-'):raise ValueError('Resolve the node conflict to remove this notification.')
                    if path.endswith('/read'):sessions.nodes.notifications(session.user_id,read=True)
                    workflows.update_notifications(session.user_id,data.get('id') if path.endswith('/delete') else None)
                    return self.json(self.notices(session))
                if path in ('/api/builder/vault-renewal','/api/builder/vault-remove'):
                    self.require_builder_node(session,ownership=True)
                    import vault_refresh
                    if path.endswith('/vault-remove'):return self.json(vault_refresh.remove(sessions.nodes.hub,session.user_id,data.get('target')))
                    return self.json(vault_refresh.start(sessions.nodes.hub,session.user_id,data.get('source'),data.get('target')))
                if path=='/api/builder/new-address':
                    self.require_builder_node(session,ownership=True)
                    BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')
                    from builder_destinations import Destinations
                    destinations=Destinations(session.preferences_path);resource=data.get('wallet_id')
                    if str(resource).startswith('receive-'):
                        prior=destinations.get(resource)
                        if prior['height']:raise ValueError('A vault policy cannot be reused from a template. Build a new vault policy explicitly.')
                        resource=prior['base']
                    current_catalog=builder_catalog(session)
                    if not any(w['id']==resource and w.get('funded_vault') for w in current_catalog['wallets']):raise ValueError('Only funded vault wallets can have a second diagram card.')
                    workspace=BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')
                    copies=[n for n in workspace.get('draft',{}).get('nodes',[]) if n['id']==resource or str(n['id']).startswith('receive-') and destinations.get(n['id'])['base']==resource]
                    if len(copies)>=2:raise ValueError('Only two cards for a funded vault wallet can be added.')
                    new=destinations.create(sessions.nodes,session.user_id,resource)
                    return self.json(next(w for w in destinations.enrich(builder_catalog(session),[new['id']])['wallets'] if w['id']==new['id']))
                if path=='/api/builder/aud-amount':
                    self.require_builder_node(session,ownership=True)
                    from fiat_amount import convert
                    return self.json(convert(data.get('aud'),fee_service.fx(),data.get('ceiling_sats')))
                if path=='/api/builder/spendability':
                    self.require_builder_node(session,ownership=True)
                    BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')
                    from vault_spending import check
                    return self.json(check(session,data))
                if path in ('/api/builder/estimate','/api/builder/preview','/api/builder/prepare'):
                    self.require_builder_node(session,ownership=True)
                    BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')
                    if not session.access()['templates_ready']:raise ValueError('Complete Ownership and save all assignments first.')
                    import re
                    diagram=clean_diagram(data.get('diagram')) if path.endswith('/prepare') else None
                    edges=diagram['edges'] if diagram else data.get('edges')
                    if not isinstance(edges,list) or not 1<=len(edges)<=256:raise ValueError('Supply 1–256 planned connections.')
                    for edge in edges:
                        if not isinstance(edge,dict) or not all(isinstance(edge.get(k),str) for k in ('from','to','amount_sats','fee_rate')):raise ValueError('Invalid planned connection.')
                        if not re.fullmatch(r'[0-9]{1,16}',edge['amount_sats']) or not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,8})?',edge['fee_rate']):raise ValueError('Invalid payment amount or fee contribution.')
                    catalog=__import__('builder_destinations').Destinations(session.preferences_path).enrich(builder_catalog(session),[n['id'] for n in diagram['nodes']] if diagram else list({e[k] for e in edges for k in ('from','to')}),sessions.nodes.hub,require_policy=True)
                    allowed={w['id'] for w in catalog['wallets'] if w['can_send']}
                    for edge in edges:
                        if type(edge.get('max',False)) is not bool or edge['to']=='network-fee' and edge.get('max'):raise ValueError('Maximum is available only for Bitcoin payments.')
                        if edge['to']=='network-fee' and int(edge['amount_sats']):raise ValueError('Network Fee connections accept only sats/vB contributions.')
                        if edge['to']!='network-fee' and Decimal(edge['fee_rate']):raise ValueError('Wallet and exchange connections accept only Bitcoin amounts.')
                    sources={edge['from'] for edge in edges if edge.get('max') or int(edge['amount_sats']) or Decimal(edge['fee_rate'])}
                    if not sources or not sources<=allowed:raise ValueError('Only loaded descriptor wallets can fund the plan.')
                    if diagram:
                        with session.lock:
                            # Ownership or profile may have changed during catalogue loading.
                            if not session.access()['templates_ready']:raise ValueError('Ownership changed. Complete Ownership and save all assignments before preparing it.')
                            workflow=WorkflowStore(session.preferences_path);created=workflow.create(session,catalog,diagram,BuilderWorkspace(session.preferences_path).owned(session.user_id,'transaction')['id'])
                            BuilderWorkspace(session.preferences_path).attach(session.user_id,'transaction',created['id'])
                            return self.json(workflow.public_job(session.user_id,created['id']))
                    coins=live_coins(session,catalog,sources)
                    if path.endswith('/preview'):return self.json(__import__('fee_planner').preview_plan(edges,catalog,coins,data.get('preview_target')))
                    return self.json(estimate_fee_plan(edges,catalog,coins))
                if path=='/api/ownership/save':
                    if not session.user() or not session.inventory_ready:raise ValueError('Scan the current input files in Ownership first.')
                    store.save_ownership(data.get('rows'),data.get('revision'),session.inventory);session.confirm_transaction_refresh();return self.json(session.family())
                if path in ('/api/start',) and not session.user():raise ValueError('Select a family user first.')
                if path=='/api/clear':session.clear_slot(data['slot'])
                elif path=='/api/start':session.start(data,data.get('mode','cgt'))
                elif path=='/api/answer':session.answer(int(data['sequence']),data['answer'])
                elif path=='/api/cancel':session.cancel()
                elif path=='/api/close':sessions.close(session.token)
                else:return self.json({'error':'Not found'},404)
                return self.json({'ok':True})
            except (ValueError,KeyError,TypeError,FileNotFoundError) as exc:
                session.record_activity('Operation stopped: '+str(exc))
                return self.json({'error':str(exc)},400)
            except Exception as exc:return self.json({'error':str(exc)},500)
    class Server(ThreadingHTTPServer):
        daemon_threads=True
    class IPv6Server(Server):
        address_family=socket.AF_INET6
        def server_bind(self):
            self.socket.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
            super().server_bind()
    listeners=[];v6_error=None
    if ipv6:
        try:listeners.append(IPv6Server(('::1',port),Handler))
        except OSError as exc:v6_error=exc
    selected_port=listeners[0].server_port if listeners else port
    if ipv4:
        try:listeners.append(Server(('127.0.0.1',selected_port),Handler))
        except OSError:
            for listener in listeners:listener.server_close()
            raise
    if not listeners:raise OSError('No requested loopback listener is available: '+str(v6_error))
    class ServerGroup:
        server_port=listeners[0].server_port
        has_ipv6=any(listener.address_family==socket.AF_INET6 for listener in listeners)
        has_ipv4=any(listener.address_family==socket.AF_INET for listener in listeners)
        listeners_started=False
        closed=False
        def __init__(self):self.reaper_stop=threading.Event();self.threads=[]
        def serve_forever(self):
            self.listeners_started=True
            for listener in listeners[1:]:
                thread=threading.Thread(target=listener.serve_forever,daemon=True);thread.start();self.threads.append(thread)
            listeners[0].serve_forever()
        def shutdown(self):
            if self.listeners_started:
                for listener in listeners:listener.shutdown()
        def server_close(self):
            if self.closed:return
            self.closed=True;self.reaper_stop.set()
            # The primary serve_forever has returned on CLI shutdown; stop
            # secondary listeners from this thread before closing their sockets.
            for listener,thread in zip(listeners[1:],self.threads):
                if thread.is_alive():listener.shutdown();thread.join(2)
            for listener in listeners:listener.server_close()
            discovery.close();fee_service.close();sessions.close_all()
    server=ServerGroup()
    def reap():
        while not server.reaper_stop.wait(60):
            sessions.expire()
            with sessions.nodes.diagnostic_log.lock:sessions.nodes.diagnostic_log.prune()
    threading.Thread(target=reap,daemon=True).start()
    return server,sessions


def main():
    parser=argparse.ArgumentParser(description='Open Wallaby Wallet in Firefox')
    parser.add_argument('--agent-port',type=int,default=DEFAULT_AGENT_PORT,help='SSH loopback agent protocol port (default: 56443)')
    parser.add_argument('--no-browser',action='store_true');parser.add_argument('--port',type=int,default=38951,help='HTTP port (default: 38951; use 0 for an automatically selected port)')
    family=parser.add_mutually_exclusive_group()
    family.add_argument('--ipv4-only',action='store_true',help='Listen on IPv4 loopback only')
    family.add_argument('--ipv6-only',action='store_true',help='Listen on IPv6 loopback only')
    parser.add_argument('--state-dir',default=str(Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'wallaby-wallet-server'))
    parser.add_argument('--max-sessions',type=int,default=32,help='Maximum simultaneous browser workspaces')
    parser.add_argument('--session-idle-hours',type=float,default=24,help='Expire disconnected idle workspaces after this interval')
    parser.add_argument('--config',default=str(ROOT/'config.cfg'),help='UTF-8 saved wallet names and ownership')
    parser.add_argument('--mobile-port',type=int,default=56444,help='SSH-loopback native mobile port (0 disables mobile connections)')
    parser.add_argument('--mobile-ssh-host-key',default='/etc/ssh/ssh_host_ed25519_key.pub',help='Local OpenSSH Ed25519 public host key for phone pairing')
    args=parser.parse_args()
    if not 0<=args.port<=65535 or not 0<=args.agent_port<=65535:parser.error('Ports must be from 0 to 65535')
    if args.port and args.port==args.agent_port:parser.error('Wallet Server and agent listeners need different ports')
    if not 0<=args.mobile_port<=65535:parser.error('Mobile port must be from 0 to 65535')
    if args.mobile_port and args.mobile_port in (args.port,args.agent_port):parser.error('Mobile, browser and Agent listeners need different ports')
    if args.max_sessions<1 or args.session_idle_hours<=0:parser.error('Session limit and idle hours must be positive')
    server,sessions=create_server(args.state_dir,args.port,args.config,args.max_sessions,args.session_idle_hours*3600,ipv6=not args.ipv4_only,ipv4=not args.ipv6_only)
    try:agent=create_agent_server(sessions.nodes,args.agent_port,sessions.profile_gate,ipv6=not args.ipv4_only,ipv4=not args.ipv6_only)
    except OSError:
        server.server_close();raise
    agent.start()
    mobile=None
    if args.mobile_port:
        try:
            from mobile_transport import create_mobile_server
            mobile=create_mobile_server(sessions.mobile,'127.0.0.1',args.mobile_port,args.mobile_ssh_host_key,sessions.profile_gate)
        except (ValueError,OSError):
            agent.close();server.server_close();raise
    host='[::1]' if server.has_ipv6 else '127.0.0.1'
    url=f'http://{host}:{server.server_port}/'
    print('Wallaby Wallet '+LABEL+' · '+str(ROOT),flush=True)
    print('Wallaby Wallet: '+url,flush=True)
    print(f'Wallaby Agent listener: loopback port {agent.server_port} (wallaby-agent JSON/HTTP v1 over SSH)',flush=True)
    print(f'Fee estimates (bookmark): http://{host}:{server.server_port}/#/fees',flush=True)
    if not server.has_ipv6 and not args.ipv4_only:print('IPv6 loopback is unavailable; using IPv4 loopback.',flush=True)
    if not args.no_browser:
        def open_browser():
            try:webbrowser.get('firefox').open(url)
            except webbrowser.Error:webbrowser.open(url)
        threading.Thread(target=open_browser,daemon=True).start()
    def stop_service(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop_service)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if mobile:mobile.shutdown();mobile.server_close()
        agent.close();server.server_close()

if __name__=='__main__':main()
