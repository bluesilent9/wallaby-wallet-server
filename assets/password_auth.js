/* The password remains in this client. HTTP carries only OPAQUE messages. */
window.WallabyAuth=(()=>{
let modulePromise;
const load=()=>modulePromise||(modulePromise=import('/assets/opaque.js').then(async m=>{await m.ready;return m;}));
async function login(user,post){
 const meta=await post('/api/auth/info',{user_id:user.id});const registering=meta.registration_required;
 return new Promise((resolve,reject)=>{
  const dialog=document.createElement('dialog');dialog.className='password-dialog';
  const form=document.createElement('form'),heading=document.createElement('h2'),description=document.createElement('p'),password=document.createElement('input'),again=document.createElement('input'),error=document.createElement('p'),submit=document.createElement('button'),cancel=document.createElement('button');
  heading.textContent=(registering?'Create a password for ':'Log in as ')+user.name;description.textContent=registering?'Your saved wallets, vault policies and builder progress will be kept. Create this account password through your trusted SSH connection. Use a strong, unique password; do not use a wallet password.':'Enter your account password. It stays on this device during the OPAQUE exchange.';
  password.type='password';password.required=true;password.autocomplete=registering?'new-password':'current-password';password.minLength=registering?12:1;password.maxLength=1024;password.setAttribute('aria-label','Password');
  again.type='password';again.required=registering;again.autocomplete='new-password';again.setAttribute('aria-label','Retype password');
  submit.type='submit';submit.className='button primary';submit.textContent=registering?'Create password and log in':'Log in';cancel.type='button';cancel.className='button outline';cancel.textContent='Cancel';error.className='error-banner';error.hidden=true;
  const finish=(result,err)=>{password.value='';again.value='';dialog.close();dialog.remove();err?reject(err):resolve(result);};cancel.onclick=()=>finish(null,new Error('Login cancelled.'));dialog.addEventListener('cancel',e=>{e.preventDefault();finish(null,new Error('Login cancelled.'));});
  const label=document.createElement('label');label.textContent='Password';label.append(password);form.append(heading,description,label);if(registering){const confirmation=document.createElement('label');confirmation.textContent='Retype password';confirmation.append(again);form.append(confirmation);}form.append(error,submit,cancel);dialog.append(form);document.body.append(dialog);dialog.showModal();password.focus();
  form.addEventListener('submit',async e=>{e.preventDefault();if(registering&&password.value!==again.value){error.hidden=false;error.textContent='The two passwords do not match.';return;}submit.disabled=true;cancel.disabled=true;error.hidden=true;
   try{const opaque=await load();let start,reply;
    if(registering){start=opaque.client.startRegistration({password:password.value});reply=await post('/api/auth/start',{user_id:user.id,mode:'register',request:start.registrationRequest});const record=opaque.client.finishRegistration({password:password.value,clientRegistrationState:start.clientRegistrationState,registrationResponse:reply.response,identifiers:{client:user.id,server:reply.server_identity},keyStretching:meta.key_stretching});start=opaque.client.startLogin({password:password.value});reply=await post('/api/auth/register',{id:reply.id,record:record.registrationRecord,request:start.startLoginRequest});}
    else{start=opaque.client.startLogin({password:password.value});reply=await post('/api/auth/start',{user_id:user.id,mode:'login',request:start.startLoginRequest});}
    const proof=opaque.client.finishLogin({password:password.value,clientLoginState:start.clientLoginState,loginResponse:reply.response,identifiers:{client:user.id,server:reply.server_identity},keyStretching:meta.key_stretching});
    if(!proof)throw Error('The password was not accepted.');const result=await post('/api/auth/finish',{id:reply.id,request:proof.finishLoginRequest});finish(result);
   }catch(e){error.hidden=false;error.textContent=e.message||'Login failed.';submit.disabled=false;cancel.disabled=false;}
  });
 });
}
return {login};})();
