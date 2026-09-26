import {auth} from '../../account/[[path]].js';
const RANK={free:0,explorer:1,research:2,pro:3};
const fail=(message,status)=>new Response(JSON.stringify({error:message}),{status,headers:{'Content-Type':'application/json','Cache-Control':'private, no-store'}});
export async function onRequestGet({request,env,params}) {
  const view=params.view, symbol=String(params.symbol||'').toUpperCase();
  if (!['price-action','results','technical-analysis'].includes(view)||!/^[A-Z0-9&._-]{1,30}$/.test(symbol))return fail('Not found',404);
  if(!env.DB)return fail('Account database unavailable',503);
  let user;
  try{user=await auth(request,env.DB)}catch{return fail('Account access unavailable',503)}
  if(!user)return fail('Sign in required',401);
  if(user.role!=='admin'&&(RANK[user.plan]||0)<RANK.research)return fail('Research plan required',403);
  let row;
  try{row=await env.DB.prepare('SELECT payload FROM research_cards WHERE symbol=? AND view=?').bind(symbol,view).first()}catch{return fail('Research storage unavailable',503)}
  if(!row)return fail('Research data has not been generated',404);
  return new Response(row.payload,{headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'}});
}
