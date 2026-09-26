// Cloudflare Pages Functions. Bind a D1 database as DB and Razorpay credentials as secrets.
const PLANS = {free:0, explorer:499, research:2999, pro:9999};
const FEATURES = [
  {id:'market',name:'Daily market, sectors and calculators',url:'/market-tools/',tier:'free'},
  {id:'strength',name:'Stock Strength Ranker',url:'/market-tools/stock-strength-ranker/',tier:'explorer'},
  {id:'momentum',name:'Momentum and Volume Surge scanners',url:'/market-tools/bullish-bearish-momentum-scanner/',tier:'explorer'},
  {id:'triggers',name:'Stock Trigger Intelligence',url:'/stock-triggers/',tier:'explorer'},
  {id:'results',name:'Result Scanner',url:'/result-scanner/',tier:'research'},
  {id:'portfolio',name:'Portfolio Analyzer',url:'/portfolio-analyzer/',tier:'research'},
  {id:'options',name:'Option Chain Sentiment',url:'/option-chain-sentiment-dashboard/',tier:'research'},
  {id:'zones',name:'Price Action Zone Finder',url:'/price-action-zone-finder/',tier:'research'},
  {id:'smart',name:'AIT Smart Move Indicator',url:'/ait-smart-move-indicator/',tier:'pro'},
  {id:'cards',name:'News and Result Impact Cards',url:'/news-card/',tier:'pro'}
];
const ranks={free:0,explorer:1,research:2,pro:3};
const encoder=new TextEncoder();
const bytesToHex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
const hexToBytes=h=>Uint8Array.from(h.match(/../g)||[],x=>parseInt(x,16));
const randomHex=n=>bytesToHex(crypto.getRandomValues(new Uint8Array(n)));
const sha=async s=>bytesToHex(await crypto.subtle.digest('SHA-256',encoder.encode(s)));
const j=(data,status=200,headers={})=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',...headers}});
async function passwordHash(password,salt){const key=await crypto.subtle.importKey('raw',encoder.encode(password),'PBKDF2',false,['deriveBits']);return bytesToHex(await crypto.subtle.deriveBits({name:'PBKDF2',salt:hexToBytes(salt),iterations:210000,hash:'SHA-256'},key,256));}
function same(a,b){if(typeof a!=='string'||typeof b!=='string'||a.length!==b.length)return false;let x=0;for(let i=0;i<a.length;i++)x|=a.charCodeAt(i)^b.charCodeAt(i);return x===0;}
function cookie(token){return `ait_session=${token}; Path=/api/account/; HttpOnly; Secure; SameSite=Strict; Max-Age=604800`;}
async function auth(req,db){const token=/\bait_session=([0-9a-f]{64})\b/.exec(req.headers.get('Cookie')||'')?.[1];if(!token)return null;return db.prepare('SELECT u.id,u.email,u.role,u.plan FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>CURRENT_TIMESTAMP').bind(await sha(token)).first();}
async function newSession(db,user){const token=randomHex(32),hash=await sha(token);await db.prepare("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,datetime('now','+7 days'))").bind(hash,user.id).run();return cookie(token);}
function account(u){return {email:u.email,role:u.role,plan:u.role==='admin'?'pro':u.plan,features:FEATURES.filter(f=>u.role==='admin'||ranks[f.tier]<=ranks[u.plan])};}
async function razor(path,env,options={}){const response=await fetch('https://api.razorpay.com/v1/'+path,{...options,headers:{Authorization:'Basic '+btoa(env.RAZORPAY_KEY_ID+':'+env.RAZORPAY_KEY_SECRET),'Content-Type':'application/json'}});const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error('Payment provider rejected the request');return data;}
async function signature(order,payment,secret){const key=await crypto.subtle.importKey('raw',encoder.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);return bytesToHex(await crypto.subtle.sign('HMAC',key,encoder.encode(order+'|'+payment)));}
export async function onRequest({request,env}){
  const url=new URL(request.url),action=url.pathname.split('/').pop(),db=env.DB;
  if(!db)return j({error:'Account database is not configured'},503);
  if(request.method==='GET'&&action==='me'){const u=await auth(request,db);return u?j(account(u)):j({error:'Sign in required'},401);}
  if(request.method!=='POST')return j({error:'Method not allowed'},405);
  const origin=request.headers.get('Origin');if(origin&&origin!==url.origin)return j({error:'Invalid origin'},403);
  const type=request.headers.get('Content-Type')||'';if(!type.includes('application/json'))return j({error:'JSON required'},415);
  let body;try{body=await request.json()}catch{return j({error:'Invalid JSON'},400)}
  const u=await auth(request,db);
  if(action==='register'){
    const email=String(body.email||'').trim().toLowerCase(),password=String(body.password||'');
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>254||password.length<12||password.length>128)return j({error:'Use a valid email and a password of 12–128 characters'},400);
    const salt=randomHex(16),hash=await passwordHash(password,salt);
    try{await db.prepare("INSERT INTO users(email,password_salt,password_hash,role,plan) VALUES(?,?,?,'customer','free')").bind(email,salt,hash).run()}catch{return j({error:'Account already exists'},409)}
    const user=await db.prepare('SELECT id,email,role,plan FROM users WHERE email=?').bind(email).first();return j(account(user),201,{'Set-Cookie':await newSession(db,user)});
  }
  if(action==='login'||action==='admin-login'){
    const email=String(body.email||'').trim().toLowerCase(),user=await db.prepare('SELECT * FROM users WHERE email=?').bind(email).first();
    // Spend comparable work even for absent accounts.
    const salt=user?.password_salt||'00000000000000000000000000000000';const candidate=await passwordHash(String(body.password||''),salt);
    if(!user||!same(candidate,user.password_hash)||Boolean(user.role==='admin')!==Boolean(action==='admin-login'))return j({error:'Invalid credentials'},401);
    return j(account(user),200,{'Set-Cookie':await newSession(db,user)});
  }
  if(action==='logout'){const token=/\bait_session=([0-9a-f]{64})\b/.exec(request.headers.get('Cookie')||'')?.[1];if(token)await db.prepare('DELETE FROM sessions WHERE token_hash=?').bind(await sha(token)).run();return j({ok:true},200,{'Set-Cookie':'ait_session=; Path=/api/account/; HttpOnly; Secure; SameSite=Strict; Max-Age=0'});}
  if(!u)return j({error:'Sign in required'},401);
  if(action==='order'){
    if(u.role!=='customer')return j({error:'Use a customer account for purchases'},403);
    const plan=String(body.plan||'');if(!['explorer','research','pro'].includes(plan))return j({error:'Unknown plan'},400);
    if(!env.RAZORPAY_KEY_ID||!env.RAZORPAY_KEY_SECRET)return j({error:'Payments are not configured'},503);
    const amount=PLANS[plan];const order=await razor('orders',env,{method:'POST',body:JSON.stringify({amount:amount*100,currency:'INR',receipt:'ait_'+u.id+'_'+Date.now(),notes:{plan,user_id:String(u.id)}})});
    await db.prepare('INSERT INTO purchases(order_id,user_id,plan,amount_paise,status) VALUES(?,?,?,?,?)').bind(order.id,u.id,plan,amount*100,'created').run();
    return j({order_id:order.id,amount:amount*100,currency:'INR',key:env.RAZORPAY_KEY_ID,plan});
  }
  if(action==='verify'){
    if(!env.RAZORPAY_KEY_SECRET)return j({error:'Payments are not configured'},503);
    const orderId=String(body.razorpay_order_id||''),paymentId=String(body.razorpay_payment_id||''),sig=String(body.razorpay_signature||'');
    if(!/^order_[\w-]+$/.test(orderId)||!/^pay_[\w-]+$/.test(paymentId)||!same(await signature(orderId,paymentId,env.RAZORPAY_KEY_SECRET),sig))return j({error:'Invalid payment signature'},400);
    const purchase=await db.prepare('SELECT * FROM purchases WHERE order_id=? AND user_id=?').bind(orderId,u.id).first();if(!purchase)return j({error:'Order not found'},404);
    const payment=await razor('payments/'+encodeURIComponent(paymentId),env);
    if(payment.order_id!==orderId||payment.amount!==purchase.amount_paise||payment.currency!=='INR'||payment.status!=='captured')return j({error:'Payment has not been captured for this order'},409);
    const outcome=await db.prepare("UPDATE purchases SET status='captured',payment_id=?,captured_at=CURRENT_TIMESTAMP WHERE order_id=? AND user_id=? AND status='created'").bind(paymentId,orderId,u.id).run();
    if(outcome.meta.changes===0){const current=await db.prepare('SELECT payment_id FROM purchases WHERE order_id=? AND user_id=?').bind(orderId,u.id).first();if(current?.payment_id!==paymentId)return j({error:'Order already assigned to another payment'},409)}
    // Never downgrade a user when buying a lower tier. All actions are safe on retry.
    await db.prepare('UPDATE users SET plan=? WHERE id=? AND role=\'customer\' AND plan IN ('+(['free','explorer','research','pro'].filter(p=>ranks[p]<ranks[purchase.plan]).map(()=>'?').join(',')||"'__none__'")+')').bind(purchase.plan,u.id,...['free','explorer','research','pro'].filter(p=>ranks[p]<ranks[purchase.plan])).run();
    const updated=await auth(request,db);return j(account(updated));
  }
  return j({error:'Unknown endpoint'},404);
}
