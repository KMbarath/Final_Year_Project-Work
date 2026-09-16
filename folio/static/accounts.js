"use strict";
let accountUser=null,signupMode=false,reminderTimer=null;
function showAuth(){
  accountUser=null;currentConversation=null;docs=[];
  document.body.classList.remove("authenticated");
  $("auth-screen").hidden=false;
  $("messages").replaceChildren();$("sources").replaceChildren();$("chat-history").replaceChildren();
  $("documents").replaceChildren();$("reminders-list").replaceChildren();$("question").value="";
  ["doc-count","nav-count","library-count","due-count","reminder-count"].forEach(id=>$(id).textContent="0");
  $("account-email").textContent="";$("auth-password").value="";
  if(reminderTimer)clearInterval(reminderTimer);
}
function updateEmailNotice(){
  $("email-notice").hidden=Boolean(status.email_configured&&accountUser.email_verified);
  $("email-notice-text").textContent=!status.email_configured
    ?"Website reminders are active. Email delivery is not configured yet."
    :"Verify "+accountUser.email+" to receive expiry reminders by email.";
  $("verify-email").hidden=!status.email_configured||accountUser.email_verified;
}
async function enterWorkspace(user){
  accountUser=user;resetChat();
  document.body.classList.add("authenticated");$("auth-screen").hidden=true;
  $("account-email").textContent=user.email;$("auth-password").value="";
  status=await api("/status");
  $("search-mode").textContent=status.embedding_model?"Hybrid":"Indexed";
  $("search-caption").textContent=status.embedding_model?"Semantic + keyword retrieval":"Keyword retrieval with sources";
  $("language").disabled=!status.translation_configured;
  updateEmailNotice();
  await refresh();await loadHistory();
  if(reminderTimer)clearInterval(reminderTimer);
  reminderTimer=setInterval(()=>{if(accountUser)loadReminders();},30000);
}
async function bootstrap(){
  try{const me=await api("/auth/me");await enterWorkspace(me.user);}
  catch(e){showAuth();if(!e.message.includes("log in"))$("auth-error").textContent=e.message;}
}
$("auth-toggle").onclick=()=>{
  signupMode=!signupMode;
  $("auth-title").textContent=signupMode?"Create your account.":"Welcome back.";
  $("auth-description").textContent=signupMode?"Save your documents, conversations and reminders in your own workspace.":"Log in to your documents, saved chats and expiry reminders.";
  $("auth-submit").textContent=signupMode?"Sign up":"Log in";
  $("auth-toggle").textContent=signupMode?"Already registered? Log in":"Create an account";
  $("auth-password").autocomplete=signupMode?"new-password":"current-password";
  $("auth-password").minLength=signupMode?10:1;$("auth-error").textContent="";
};
$("auth-form").onsubmit=async e=>{
  e.preventDefault();$("auth-submit").disabled=true;$("auth-error").textContent="";
  try{
    const result=await api(signupMode?"/auth/signup":"/auth/login",body({email:$("auth-email").value,password:$("auth-password").value}));
    await enterWorkspace(result.user);
    if(result.verification_email==="sent")toast("Check your email for the verification link.");
    if(result.verification_email==="failed")toast("Account created. Verification email failed; you can retry from the notice above.");
  }catch(e){showAuth();$("auth-error").textContent=e.message;}finally{$("auth-submit").disabled=false;}
};
$("logout").onclick=async()=>{try{await api("/auth/logout",body({}));showAuth();}catch(e){toast(e.message);}};
$("verify-email").onclick=async()=>{
  $("verify-email").disabled=true;
  try{const r=await api("/auth/resend-verification",body({}));toast(r.verification_email==="sent"?"Verification email sent. Check your inbox.":"Verification status: "+r.verification_email);}
  catch(e){toast(e.message);}finally{$("verify-email").disabled=false;}
};
