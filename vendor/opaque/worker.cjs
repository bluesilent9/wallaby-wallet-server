// Narrow stdin/stdout adapter. Passwords and client state never enter this process.
const opaque=require('./server.cjs');
let input='';process.stdin.on('data',d=>{input+=d;if(input.length>32768)process.exit(2);});
process.stdin.on('end',async()=>{try{await opaque.ready;const {action,params}=JSON.parse(input);const methods={setup:opaque.server.createSetup,publicKey:opaque.server.getPublicKey,register:opaque.server.createRegistrationResponse,start:opaque.server.startLogin,finish:opaque.server.finishLogin};if(!methods[action])throw Error('action');const result=methods[action](params);process.stdout.write(JSON.stringify(result));}catch{process.stderr.write('OPAQUE request rejected');process.exitCode=1;}});
