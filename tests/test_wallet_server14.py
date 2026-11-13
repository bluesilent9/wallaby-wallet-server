"""Selected-key forwarding repair, including a real isolated OpenSSH tunnel."""
import base64,copy,http.server,json,os,socket,stat,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ssh_access as access

class KeyRepair(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.ssh=self.root/'.ssh';self.ssh.mkdir(mode=0o700);self.key=self.root/'testkey';subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(self.key)],check=True);self.public=' '.join(self.key.with_suffix('.pub').read_text().split()[:2]);self.original='restrict,port-forwarding,permitopen="[::1]:8096",command="/bin/false" '+self.public+' test device\n';self.auth=self.ssh/'authorized_keys';self.auth.write_text(self.original);self.auth.chmod(0o600)
 def test_remove_only_port_limits_from_one_key_preserves_other_options_and_entries(self):
  row='from="192.0.2.0/24",restrict,no-port-forwarding,permitopen="127.0.0.1:1",permitlisten="[::1]:2",command="echo a,b c" '+self.public+' comment\r\n';data='# existing comment\r\n'+row+self.original
  out,fp=access.allow_all_ports(data,2);self.assertEqual(out,'# existing comment\r\n'+'from="192.0.2.0/24",restrict,command="echo a,b c",port-forwarding '+self.public+' comment\r\n'+self.original);self.assertTrue(fp.startswith('SHA256:'))
 def test_plain_keys_unchanged_and_restrict_requires_explicit_port_forwarding(self):
  data=self.public+' comment\n';self.assertEqual(access.allow_all_ports(data,1)[0],data)
  data='port-forwarding,restrict '+self.public+'\n';changed=access.allow_all_ports(data,1)[0];self.assertTrue(changed.startswith('restrict,port-forwarding '));self.assertEqual(access.allow_all_ports(changed,1)[0],changed)
 def test_invalid_entry_and_fingerprint_fail_without_editing(self):
  for entry in (0,2,-1):
   with self.assertRaises(ValueError):access.allow_all_ports(self.original,entry)
  with self.assertRaises(ValueError):access.allow_all_ports(self.original,1,'SHA256:other')
  with self.assertRaises(ValueError):access.allow_all_ports('# comment\n',1)
  with self.assertRaises(ValueError):access.allow_all_ports('command="unclosed '+self.public,1)
 def test_audit_does_not_print_key_material_or_forced_command(self):
  result=access.describe(self.original);text=json.dumps(result);self.assertNotIn(self.public.split()[1],text);self.assertNotIn('/bin/false',text);self.assertIn('permitopen',text)
 def test_dry_run_does_not_write_and_apply_keeps_backup_ownership_and_mode(self):
  info=self.auth.stat();out=access.repair(str(self.root),os.getuid(),os.getgid(),1);self.assertTrue(out['changed']);self.assertFalse(out['applied']);self.assertEqual(self.auth.read_text(),self.original);self.assertEqual(len(list(self.ssh.iterdir())),1)
  with patch('ssh_access.os.geteuid',return_value=0):out=access.repair(str(self.root),os.getuid(),os.getgid(),1,apply=True)
  self.assertTrue(out['applied']);self.assertEqual((self.ssh/out['backup']).read_bytes(),self.original.encode());self.assertEqual(self.auth.read_text(),access.allow_all_ports(self.original,1)[0]);after=self.auth.stat();self.assertEqual((after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode)),(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)))
  with patch('ssh_access.os.geteuid',return_value=0):again=access.repair(str(self.root),os.getuid(),os.getgid(),1,apply=True)
  self.assertFalse(again['changed']);self.assertEqual(len(list(self.ssh.glob('*.bak'))),1)
 def test_refuses_symlink_hardlink_and_writable_authorized_file(self):
  self.auth.chmod(0o666)
  with self.assertRaises(ValueError):access.repair(str(self.root),os.getuid(),os.getgid(),1,apply=True)
  self.auth.chmod(0o600);linked=self.root/'linked';os.link(self.auth,linked)
  with self.assertRaises(ValueError):access.repair(str(self.root),os.getuid(),os.getgid(),1,apply=True)
  linked.unlink();self.auth.rename(linked);self.auth.symlink_to(linked)
  with self.assertRaises(OSError):access.repair(str(self.root),os.getuid(),os.getgid(),1,apply=True)
  self.assertEqual(linked.read_text(),self.original)
 def test_refuses_non_root_apply_and_global_account_restrictions(self):
  with patch('ssh_access.os.geteuid',return_value=1000):
   with self.assertRaisesRegex(ValueError,'sudo'):access.repair(str(self.root),os.getuid(),os.getgid(),1,apply=True)
  account=type('Account',(),{'pw_dir':str(self.root),'pw_uid':os.getuid(),'pw_gid':os.getgid()})()
  policy={'authorizedkeysfile':'.ssh/authorized_keys','allowtcpforwarding':'yes','disableforwarding':'no','permitopen':'any','permitlisten':'any'}
  for key,value in (('allowtcpforwarding','no'),('disableforwarding','yes'),('permitopen','[::1]:8096')):
   with patch('ssh_access.pwd.getpwnam',return_value=account),patch('ssh_access.effective',return_value={**policy,key:value}),patch('ssh_access.repair') as repair,patch('sys.stderr'):
    self.assertEqual(access.main(['--user','example','--entry','1','--allow-all-ports','--apply']),1);repair.assert_not_called()
 def test_concurrent_file_replacement_does_not_overwrite_other_editor(self):
  oldstat=os.stat
  def altered(path,*args,**kw):
   if path=='authorized_keys' and kw.get('follow_symlinks') is False:self.auth.write_text(self.original+'# concurrent edit\n')
   return oldstat(path,*args,**kw)
  with patch('ssh_access.os.geteuid',return_value=0),patch('ssh_access.os.stat',side_effect=altered):
   with self.assertRaisesRegex(ValueError,'changed during'):access.repair(str(self.root),os.getuid(),os.getgid(),1,apply=True)
  self.assertIn('# concurrent edit',self.auth.read_text());self.assertFalse(list(self.ssh.glob('.authorized_keys.wallaby-*')))

class OpenSSH(KeyRepair):
 def test_ipv4_login_and_ipv6_destinations_reproduce_denial_then_succeed(self):
  binary=os.environ.get('WALLABY_TEST_SSHD')
  if not binary:self.skipTest('Set extracted official OpenSSH server path')
  binary=Path(binary).resolve();lib=binary.parents[1]/'lib/openssh';host=self.root/'host';subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(host)],check=True)
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  config=self.root/'sshd.conf';log=self.root/'sshd.log';config.write_text(f'''Port {port}
ListenAddress 127.0.0.1
HostKey {host}
PidFile {self.root}/sshd.pid
AuthorizedKeysFile {self.auth}
StrictModes no
UsePAM no
PasswordAuthentication no
KbdInteractiveAuthentication no
AllowTcpForwarding yes
PermitOpen any
PermitListen any
SshdSessionPath {lib}/sshd-session
SshdAuthPath {lib}/sshd-auth
LogLevel VERBOSE
''')
  stream=log.open('wb');process=subprocess.Popen([str(binary),'-D','-e','-f',str(config)],stderr=stream,stdout=subprocess.DEVNULL);stream.close();self.addCleanup(lambda: process.poll() is None and process.terminate());deadline=time.monotonic()+5
  while True:
   if process.poll() is not None:self.fail(log.read_text())
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:
    if time.monotonic()>deadline:self.fail(log.read_text())
    time.sleep(.05)
  class Handler(http.server.BaseHTTPRequestHandler):
   def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'isolated tunnel success')
   def log_message(self,*args):pass
  class Server(http.server.HTTPServer):address_family=socket.AF_INET6
  servers=[Server(('::1',0),Handler) for _ in range(2)]
  for server in servers:
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  import pwd
  user=pwd.getpwuid(os.getuid()).pw_name
  def probe(server):return subprocess.run(['ssh','-F','/dev/null','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=3','-i',str(self.key),'-p',str(port),'-W','[::1]:'+str(server.server_port),user+'@127.0.0.1'],input=b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n',capture_output=True,timeout=8)
  denied=probe(servers[0]);self.assertNotEqual(denied.returncode,0);self.assertIn(b'administratively prohibited',denied.stderr)
  with patch('ssh_access.os.geteuid',return_value=0):access.repair(str(self.root),os.getuid(),os.getgid(),1,apply=True)
  for server in servers:
   allowed=probe(server);self.assertEqual(allowed.returncode,0,allowed.stderr.decode()+log.read_text());self.assertIn(b'isolated tunnel success',allowed.stdout)
  process.terminate();process.wait(3)

# Run the helper unit checks once, not again through fixture inheritance.
for name in KeyRepair.__dict__:
 if name.startswith('test_') and name not in OpenSSH.__dict__:setattr(OpenSSH,name,None)
if __name__=='__main__':unittest.main()
