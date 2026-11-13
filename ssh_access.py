#!/usr/bin/env python3
"""Administrator-only SSH key forwarding repair; never run during installation.

Wallet application users and operating-system SSH accounts are independent.
Only an explicitly selected authorised key entry is changed. No key material,
command restrictions or other accounts are printed or silently rewritten.
"""
import argparse,base64,fcntl,hashlib,json,os,pwd,re,secrets,shlex,stat,subprocess,sys

MAX_FILE=1024*1024
PORT_OPTIONS={'permitopen','permitlisten','no-port-forwarding','port-forwarding'}
KEY=re.compile(r'(?:ssh-(?:ed25519|rsa|dss)|ecdsa-sha2-[A-Za-z0-9-]+|sk-[A-Za-z0-9@.-]+)(?:-cert-v01@openssh.com)?$')

def fields(line):
    """Split the option prefix without changing quoted commands/comments."""
    quoted=False;escaped=False
    for i,c in enumerate(line):
        if escaped:escaped=False;continue
        if c=='\\':escaped=True;continue
        if c=='"':quoted=not quoted
        if c.isspace() and not quoted:break
    else:i=len(line)
    if quoted or escaped:raise ValueError('Malformed authorised-key quoting; no changes made.')
    prefix=line[:i];rest=line[i:].lstrip()
    if KEY.fullmatch(prefix):return [],line
    opts=[];start=0;quoted=False;escaped=False
    for j,c in enumerate(prefix):
        if escaped:escaped=False;continue
        if c=='\\':escaped=True;continue
        if c=='"':quoted=not quoted
        if c==',' and not quoted:opts.append(prefix[start:j]);start=j+1
    opts.append(prefix[start:])
    if not rest or any(not o for o in opts):raise ValueError('Malformed authorised-key options; no changes made.')
    return opts,rest

def fingerprint(rest):
    parts=rest.split()
    if len(parts)<2 or not KEY.fullmatch(parts[0]):raise ValueError('Unsupported authorised-key entry; no changes made.')
    try:
        raw=base64.b64decode(parts[1],validate=True);n=int.from_bytes(raw[:4],'big')
        if not 0<n<256 or raw[4:4+n].decode()!=parts[0] or len(raw)>16384:raise ValueError()
    except (ValueError,UnicodeError):raise ValueError('Invalid public-key encoding; no changes made.') from None
    return 'SHA256:'+base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')

def describe(data):
    result=[]
    for n,line in enumerate(data.splitlines(),1):
        text=line.strip()
        if not text or text.startswith('#'):continue
        options,rest=fields(text);fp=fingerprint(rest)
        result.append({'entry':n,'fingerprint':fp,'port_options':[o for o in options if o.split('=',1)[0] in PORT_OPTIONS or o=='restrict']})
    return result

def allow_all_ports(data,entry,expected=None):
    lines=data.splitlines(keepends=True)
    if type(entry) is not int or not 1<=entry<=len(lines):raise ValueError('Select an existing entry line; no changes made.')
    original=lines[entry-1];text=original.strip()
    if not text or text.startswith('#'):raise ValueError('Selected line is not a key; no changes made.')
    options,rest=fields(text);fp=fingerprint(rest)
    if expected and fp!=expected:raise ValueError('Selected key fingerprint changed; no changes made.')
    keep=[o for o in options if o.split('=',1)[0] not in PORT_OPTIONS]
    # restrict disables forwarding implicitly. Restore only port forwarding;
    # keep forced commands, no-PTY, agent/X11 restrictions and source limits.
    if 'restrict' in keep:keep.append('port-forwarding')
    if keep==options:return data,fp
    ending='\r\n' if original.endswith('\r\n') else '\n' if original.endswith('\n') else ''
    indent=original[:len(original)-len(original.lstrip())]
    lines[entry-1]=indent+(','.join(keep)+' ' if keep else '')+rest+ending
    return ''.join(lines),fp

def write_all(fd,data):
    view=memoryview(data)
    while view:
        n=os.write(fd,view)
        if not n:raise OSError('Short write')
        view=view[n:]

def repair(home,uid,gid,entry,expected=None,apply=False):
    """Dir-fd/no-follow writes and a private backup avoid symlink replacement."""
    homefd=os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    sshfd=None;authfd=None;temp=None
    try:
        sshfd=os.open('.ssh',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=homefd)
        directory=os.fstat(sshfd)
        if directory.st_uid not in (0,uid) or directory.st_mode&0o022:raise ValueError('Unsafe SSH directory ownership or permissions; no changes made.')
        authfd=os.open('authorized_keys',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=sshfd);fcntl.flock(authfd,fcntl.LOCK_EX)
        info=os.fstat(authfd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0,uid) or info.st_mode&0o022 or info.st_nlink!=1:raise ValueError('Unsafe authorised-key file; no changes made.')
        raw=os.read(authfd,MAX_FILE+1)
        if len(raw)>MAX_FILE:raise ValueError('Authorised-key file exceeds size limit; no changes made.')
        data=raw.decode('utf-8');result={'keys':describe(data),'changed':False,'applied':False}
        if entry is None:return result
        changed,fp=allow_all_ports(data,entry,expected);result.update(fingerprint=fp,changed=changed!=data)
        if not apply or changed==data:
            if changed!=data:result['proposed_keys']=describe(changed)
            return result
        if os.geteuid()!=0:raise ValueError('Apply requires sudo; no changes made.')
        suffix=secrets.token_hex(12);backup='authorized_keys.wallaby-'+suffix+'.bak'
        fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=sshfd)
        try:os.fchown(fd,info.st_uid,info.st_gid);write_all(fd,raw);os.fsync(fd)
        finally:os.close(fd)
        temp='.authorized_keys.wallaby-'+suffix
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=sshfd)
        try:os.fchown(fd,info.st_uid,info.st_gid);os.fchmod(fd,stat.S_IMODE(info.st_mode));write_all(fd,changed.encode());os.fsync(fd)
        finally:os.close(fd)
        # An unrelated editor must not be overwritten after our initial read.
        current=os.stat('authorized_keys',dir_fd=sshfd,follow_symlinks=False)
        if (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns)!=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns):raise ValueError('Authorised keys changed during repair; retry after reviewing them.')
        os.replace(temp,'authorized_keys',src_dir_fd=sshfd,dst_dir_fd=sshfd);temp=None;os.fsync(sshfd)
        result.update(applied=True,backup=backup,keys_before=result['keys'],keys=describe(changed));return result
    finally:
        if temp and sshfd is not None:
            try:os.unlink(temp,dir_fd=sshfd)
            except FileNotFoundError:pass
        for fd in (authfd,sshfd,homefd):
            if fd is not None:os.close(fd)

def effective(user,client_address):
    p=subprocess.run(['/usr/sbin/sshd','-T','-C','user='+user+',host=localhost,addr='+client_address],capture_output=True,text=True,timeout=10)
    if p.returncode:raise ValueError('Cannot check effective sshd policy. Run with sudo and validate sshd configuration.')
    wanted={'allowtcpforwarding','disableforwarding','permitopen','permitlisten','authorizedkeysfile'}
    return dict(line.split(None,1) for line in p.stdout.splitlines() if line.split() and line.split()[0] in wanted)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--user',required=True);parser.add_argument('--entry',type=int);parser.add_argument('--expected-fingerprint');parser.add_argument('--client-address',default='127.0.0.1');parser.add_argument('--allow-all-ports',action='store_true');parser.add_argument('--apply',action='store_true');args=parser.parse_args(argv)
    try:
        if (args.entry is not None)!=args.allow_all_ports or args.apply and args.entry is None:raise ValueError('Changing a key requires --entry and --allow-all-ports; --apply is explicit.')
        if any(c in args.user+args.client_address for c in (',','\n','\r')):raise ValueError('Invalid SSH account or client address.')
        account=pwd.getpwnam(args.user);policy=effective(args.user,args.client_address)
        if policy.get('authorizedkeysfile') not in ('.ssh/authorized_keys','.ssh/authorized_keys .ssh/authorized_keys2'):raise ValueError('Custom AuthorizedKeysFile: use the system administrator; no changes made.')
        if args.apply and (policy.get('allowtcpforwarding')!='yes' or policy.get('disableforwarding')!='no' or policy.get('permitopen')!='any' or policy.get('permitlisten')!='any'):raise ValueError('Account forwarding is restricted by sshd. No key changes made; no global rules were altered.')
        result=repair(account.pw_dir,account.pw_uid,account.pw_gid,args.entry,args.expected_fingerprint,args.apply);result['account_policy']=policy;result['user']=args.user;print(json.dumps(result,indent=2));return 0
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        print('SSH access check/repair failed: '+str(exc),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
