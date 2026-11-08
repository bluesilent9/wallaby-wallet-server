"""SSH-loopback native mobile listener, isolated from browser/Agent APIs."""
import ipaddress,json,socket,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from pathlib import Path
from setup_signatures import fingerprint

def unique(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Duplicate JSON field.')
        result[key]=value
    return result

def create_mobile_server(devices,host,port,host_key_file,gate):
    if not ipaddress.ip_address(host).is_loopback:raise ValueError('The mobile listener must be SSH-loopback only.')
    public=' '.join(Path(host_key_file).read_text().split()[:2]) if Path(host_key_file).is_file() else None
    if public:fingerprint(public)
    class Handler(BaseHTTPRequestHandler):
        server_version='WallabyWalletMobile/1'
        def log_message(self,*args):pass
        def setup(self):
            super().setup();self.connection.settimeout(10)
        def reply(self,value,status=200):
            body=json.dumps(value,separators=(',',':')).encode();self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
        def do_GET(self):self.reply({'error':'Native mobile POST requests are required.'},405)
        def do_POST(self):
            from launch_wallaby_wallet_server import loopback_authority
            hosts=self.headers.get_all('Host',[])
            if len(hosts)!=1 or not loopback_authority(hosts[0]) or self.headers.get_all('X-Wallaby-Mobile',[])!=['1'] or self.headers.get_all('Origin') or self.headers.get_all('Cookie') or self.headers.get_all('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':return self.reply({'error':'A native mobile request through SSH is required.'},403)
            try:
                lengths=self.headers.get_all('Content-Length',[])
                if len(lengths)!=1 or not lengths[0].isdigit() or not 0<int(lengths[0])<=70000:raise ValueError('Invalid mobile request size.')
                raw=self.rfile.read(int(lengths[0]))
                if len(raw)!=int(lengths[0]):raise ValueError('Incomplete mobile request.')
                data=json.loads(raw,object_pairs_hook=unique)
                if not isinstance(data,dict):raise ValueError('A JSON object is required.')
                path=urlsplit(self.path).path
                # Profile replacement invalidates sessions before any new access.
                with gate.access():
                    if path=='/mobile/v1/pair':return self.reply(devices.join(data))
                    if path=='/mobile/v1/challenge':return self.reply(devices.challenge(data.get('device_id')))
                    if path=='/mobile/v1/connect':return self.reply(devices.connect(data.get('proof')))
                    auth=self.headers.get_all('Authorization',[])
                    if len(auth)!=1 or not auth[0].startswith('Bearer '):return self.reply({'error':'Connect this paired mobile device first.'},401)
                    token=auth[0][7:]
                    if path=='/mobile/v1/relay':return self.reply(devices.hub.relay.dispatch(devices.hub.relay.mobile(devices,token),data))
                    if path.startswith('/mobile/v1/auth/'):
                        return self.reply(devices.authenticate(token,path.rsplit('/',1)[1],data))
                    if path=='/mobile/v1/data':
                        if set(data)!={'section'}:raise ValueError('Choose a data section.')
                        return self.reply(devices.data(token,data['section']))
                    if path=='/mobile/v1/claims':return self.reply(devices.claims(token))
                    if path=='/mobile/v1/result':return self.reply(devices.result(token,data.get('proof')))
                    return self.reply({'error':'Unknown mobile endpoint.'},404)
            except (ValueError,KeyError,TypeError,UnicodeError):return self.reply({'error':'Mobile request rejected. Reconnect or pair again if the invitation expired.'},400)
            except OSError:return self.reply({'error':'Mobile service is unavailable.'},503)
    class Server(ThreadingHTTPServer):
        address_family=socket.AF_INET6 if ':' in host else socket.AF_INET
        daemon_threads=True
        slots=threading.BoundedSemaphore(16)
        def process_request(self,request,address):
            if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
            try:super().process_request(request,address)
            except BaseException:self.slots.release();raise
        def process_request_thread(self,request,address):
            try:super().process_request_thread(request,address)
            finally:self.slots.release()
    server=Server((host,port),Handler)
    devices.mobile_port=server.server_port;devices.ssh_host_public_key=public
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    return server
