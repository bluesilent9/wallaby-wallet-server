"""CGT warning thresholds, unread lifecycle and offline saved reports."""
import unittest,tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from run_freshness import warning
from transaction_workflows import WorkflowStore
class Freshness(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.config=Path(self.tmp.name)/'config.cfg';self.now=datetime(2026,11,18,8,tzinfo=timezone.utc)
 def value(self,days):return warning(self.config,{'cgt_completed_utc':(self.now-timedelta(days=days)).isoformat()},'2026-11-18','Australia/Sydney',now=self.now)
 def test_thresholds(self):
  self.assertIsNone(self.value(7));self.assertEqual(self.value(7.001)['severity'],'yellow');self.assertEqual(self.value(30)['severity'],'yellow');self.assertEqual(self.value(30.001)['severity'],'red')
 def test_only_cgt_and_utc_timestamp(self):
  self.assertIsNone(warning(self.config,{'ownership_runs':{'u':{'completed_utc':'2020-01-01T00:00:00Z'}}},'2026-11-18',now=self.now));n=self.value(8);self.assertIn('10/11/2026 08:00:00 UTC',n['text']);self.assertFalse(n['dismissible']);self.assertFalse(n['read'])
 def test_unread_created_from_unrelated_page_then_relevant_page_marks_read(self):
  store=WorkflowStore(self.config)
  with patch('run_freshness.warning',return_value=self.value(8)):
   store.sync_run_warning('u','2026-11-18','UTC','balances',{});n=store.notifications('u')['notifications'][0];self.assertFalse(n['read'])
   store.sync_run_warning('u','2026-11-18','UTC','nodes',{});self.assertFalse(store.notifications('u')['notifications'][0]['read'])
   store.sync_run_warning('u','2026-11-18','UTC','history',{});self.assertTrue(store.notifications('u')['notifications'][0]['read'])
   with self.assertRaises(ValueError):store.update_notifications('u',delete=n['id'])
 def test_escalation_retains_id_and_read_until_new_report(self):
  store=WorkflowStore(self.config);yellow=self.value(8);red=dict(yellow,severity='red',age_days=31)
  with patch('run_freshness.warning',return_value=yellow):store.sync_run_warning('u','2026-11-18','UTC','totals',{})
  old=store.notifications('u')['notifications'][0]
  with patch('run_freshness.warning',return_value=red):store.sync_run_warning('u','2026-11-18','UTC','balances',{})
  new=store.notifications('u')['notifications'][0];self.assertEqual(new['id'],old['id']);self.assertTrue(new['read']);self.assertEqual(new['severity'],'red')
  with patch('run_freshness.warning',return_value=None):store.sync_run_warning('u','2026-11-18','UTC','balances',{})
  self.assertEqual(store.notifications('u')['notifications'],[])
 def test_old_ownership_notice_is_removed_everywhere(self):
  store=WorkflowStore(self.config);data=store._read();data['notices']={'u':[{'id':'old','kind':'run_freshness','run_kind':'ownership','read':True}]};store._write(data)
  with patch('run_freshness.warning',return_value=None):store.sync_run_warning('u','2026-11-18','UTC','admin',{})
  self.assertEqual(store.notifications('u')['notifications'],[])
 def test_node_disconnect_notice_clears_on_reconnect(self):
  store=WorkflowStore(self.config);store.sync_node_warning('u',False,'admin');n=store.notifications('u')['notifications'][0];self.assertEqual(n['text'],'Node not connected. Data may be out of date.');self.assertFalse(n['read']);self.assertFalse(n['dismissible'])
  store.sync_node_warning('u',False,'nodes');self.assertTrue(store.notifications('u')['notifications'][0]['read']);store.sync_node_warning('u',True,'admin');self.assertEqual(store.notifications('u')['notifications'],[])
