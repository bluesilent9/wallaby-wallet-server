const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const context={window:{}};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(process.argv[2],'password_auth.js'),'utf8'),context);const check=context.window.WallabyAuth.passwordError;
for(const p of ['abcde1!f','abcdef1£','a 1!bcde','A'.repeat(1022)+'1!'])assert.equal(check(p),'',p.length);
for(const p of ['', 'abcd1!e','abcdefgh','abcdefg!','abcdef12','abcdef1 ','ABCDEF1\n','abcdef１!','A'.repeat(1023)+'1!'])assert(check(p),JSON.stringify(p));
console.log('PASS password creation boundaries, digit/symbol requirements, spaces, Unicode symbols and maximum length.');
