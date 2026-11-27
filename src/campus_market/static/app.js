/* Vanilla browser UI. All authorization and state transitions remain on the server. */
'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const user = {id: document.body.dataset.userId, role: document.body.dataset.role};
const labels = Object.fromEntries([...$('#status-options').content.children].map(o => [o.value,o.textContent]));
const badge = state => `<span class="badge ${esc(state)}">${esc(labels[state] || state)}</span>`;
const categoryOptions = $('#category-options').innerHTML;
const conditionOptions = $('#condition-options').innerHTML;
const content = $('#content');
const heading = $('#page-heading');
const modal = $('#modal');
let currentPage = 1;
let activeLoader = null;
const pendingCommands = new Map();
const csrf = () => decodeURIComponent(document.cookie.split('; ').find(v=>v.startsWith('campus_csrf='))?.split('=')[1] || '');
function feedback(message, success=false) {
  const el=$('#feedback'); el.textContent=message; el.className=success?'success':''; el.hidden=false;
}
async function api(url, options={}) {
  const response=await fetch(url,{credentials:'same-origin',...options,headers:{'X-CSRF-Token':csrf(),...options.headers}});
  const data=await response.json();
  if(!response.ok) throw new Error(`${data.message || '操作失败'}${data.field?'（'+data.field+'）':''}`);
  return data;
}
async function command(url, data, method='POST') {
  const signature=method+' '+url+' '+JSON.stringify(data);
  const key=pendingCommands.get(signature)||crypto.randomUUID();
  pendingCommands.set(signature,key);
  try {
    const response=await fetch(url,{method,credentials:'same-origin',headers:{'Content-Type':'application/json',
      'X-CSRF-Token':csrf(),'Idempotency-Key':key},body:JSON.stringify(data)});
    const result=await response.json();
    if(response.status<500) pendingCommands.delete(signature);
    if(!response.ok) throw new Error(result.message || '操作失败，请保留输入并重试');
    pendingCommands.delete(signature);
    return result;
  } catch(error) {throw error;}
}
function title(name, subtitle, action='') {
  heading.innerHTML=`<div class="heading-row"><div><div class="eyebrow">CAMPUS MARKETPLACE</div><h1>${name}</h1><div class="subtitle">${subtitle}</div></div>${action}</div>`;
}
function openModal(name, html) {
  $('#modal-title').textContent=name; $('#modal-body').innerHTML=html; modal.showModal();
}
function formHandler(form, callback) {
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const button=$('button[type=submit]',form); if(button) button.disabled=true;
    let error=$('.inline-error',form);
    if(!error){error=document.createElement('div');error.className='inline-error';form.prepend(error);}
    error.textContent='';
    try {await callback(Object.fromEntries(new FormData(form)),form);}
    catch(exc){error.textContent=exc.message;}
    finally{if(button)button.disabled=false;}
  });
}
function dateText(value) {return value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '—';}
function empty() {return '<div class="panel empty"><strong>这里还没有记录</strong>试着调整筛选条件，或先发布一件闲置好物。</div>';}
function pager(total) {
  const max=Math.max(1,Math.ceil(total/20));
  return `<div class="pager"><button class="secondary small" data-page="${currentPage-1}" ${currentPage<=1?'disabled':''}>上一页</button><span>第 ${currentPage} / ${max} 页 · 共 ${total} 条</span><button class="secondary small" data-page="${currentPage+1}" ${currentPage>=max?'disabled':''}>下一页</button></div>`;
}
function bindPager() {
  document.querySelectorAll('[data-page]').forEach(el=>el.onclick=async()=>{
    currentPage=Number(el.dataset.page); await activeLoader();
  });
}
function productFilters(admin=false) {
  return `<form id="filters" class="panel filters"><label class="wide">关键词<input name="keyword" placeholder="搜索标题或描述"></label><label>分类<select name="category"><option value="">全部分类</option>${categoryOptions}</select></label><label>最低价<input name="min_price" inputmode="decimal" placeholder="不限"></label><label>最高价<input name="max_price" inputmode="decimal" placeholder="不限"></label>${admin?'<label>状态<select name="status"><option value="">全部状态</option>'+['DRAFT','PENDING','REJECTED','SALE','RESERVED','OFF','VIOLATED','SOLD'].map(s=>`<option value="${s}">${labels[s]}</option>`).join('')+'</select></label>':''}<label>排序<select name="sort"><option value="latest">最近发布</option><option value="price_asc">价格从低到高</option><option value="price_desc">价格从高到低</option></select></label><button type="submit" class="filter-button">查询</button></form><div id="results"></div>`;
}
async function listProducts(mode) {
  const mine=mode==='mine',admin=mode==='admin';
  title(mine?'我的商品':admin?'商品审核与治理':'发现身边的好物',mine?'管理你的闲置物品，查看发布进度与交易状态。':admin?'按当前审核批次处理；违规下架会同步终止有效预约。':'好物值得再次相遇。浏览在售商品，与卖家预约线下交付。',mine?'<button id="create-product">＋ 发布商品</button>':'');
  content.innerHTML=productFilters(mine||admin);
  if(mine) $('#create-product').onclick=()=>editProduct();
  const endpoint=mine?'/api/me/products':admin?'/api/admin/products':'/api/products';
  activeLoader=async()=>{
    const params=new URLSearchParams(new FormData($('#filters'))); params.set('page',currentPage);
    const data=await api(endpoint+'?'+params);
    $('#results').innerHTML=`<div class="list-summary"><span>${admin?'管理范围：全部非草稿商品':mine?'仅显示本人商品':'公开范围：在售商品'}</span><span>共 ${data.total} 件</span></div>`+(data.items.length?`<div class="cards">${data.items.map(p=>`<article class="card"><a href="/product/${p.id}" class="product-image">${p.image_ids.length?`<img src="/images/${p.image_ids[0]}" alt="${esc(p.title)}">`:'拾光'}</a><div class="card-body"><a class="card-title" href="/product/${p.id}">${esc(p.title)}</a><div class="card-meta">${esc(p.category||'未分类')} · ${esc(p.condition||'未填写成色')}</div><div class="card-bottom"><div class="price"><small>¥</small>${esc(p.price||'未定价')}</div>${badge(p.status)}</div></div></article>`).join('')}</div>`:empty())+pager(data.total);
    bindPager();
  };
  formHandler($('#filters'),async()=>{currentPage=1;await activeLoader();});
  await activeLoader();
}
async function editProduct(product=null) {
  const p=product||{}; let images=[...(p.image_ids||[])];
  openModal(p.id?'编辑商品':'发布闲置商品',`<form id="product-form"><div class="form-grid"><label class="full">标题 *<input name="title" maxlength="200" required value="${esc(p.title)}"></label><label>分类<select name="category"><option value="">暂不填写</option>${categoryOptions}</select></label><label>成色<select name="condition"><option value="">暂不填写</option>${conditionOptions}</select></label><label class="full">价格（元）<input name="price" inputmode="decimal" value="${esc(p.price)}" placeholder="0.01～99999.99，最多两位小数"></label><label class="full">商品描述<textarea name="description" maxlength="500">${esc(p.description)}</textarea></label></div><label>商品图片（最多3张，每张≤5MB，JPG/PNG）<input id="image-files" type="file" accept="image/jpeg,image/png" multiple></label><div class="image-row" id="chosen-images"></div><p class="help">草稿标题非空即可保存；提交审核时标题须为2～50字，并填写分类、成色和价格。在售商品保存修改后立即回到草稿，重新审核后才公开。</p><button type="submit">保存草稿</button></form>`);
  const form=$('#product-form'); form.elements.category.value=p.category||'';form.elements.condition.value=p.condition||'';
  const drawImages=()=>{
    $('#chosen-images').innerHTML=images.map(id=>`<div><img src="/images/${id}" alt="商品图片"><button type="button" class="secondary" data-remove="${id}">移除</button></div>`).join('');
    document.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{images=images.filter(id=>id!==b.dataset.remove);drawImages();});
  }; drawImages();
  $('#image-files').onchange=async event=>{
    try{
      const files=[...event.target.files];if(images.length+files.length>3)throw new Error('最多选择3张图片');
      for(const file of files){const data=new FormData();data.append('file',file);const saved=await api('/api/images',{method:'POST',body:data});images.push(saved.id);}
      drawImages();
    }catch(exc){feedback(exc.message);$('.inline-error',form)?.remove();const err=document.createElement('p');err.className='inline-error';err.textContent=exc.message;form.prepend(err);}
    finally{event.target.value='';}
  };
  formHandler(form,async data=>{
    data.image_ids=images;data.price=data.price||null;
    if(p.id){data.expected_row_version=p.row_version;data.content_version=p.content_version;}
    const result=await command(p.id?'/api/products/'+p.id:'/api/products',data,p.id?'PATCH':'POST');
    modal.close();location.href='/product/'+result.object.id;
  });
}
async function reasonModal(name, callback, notice='请填写具体原因（1～200字）。') {
  openModal(name,`<form id="reason-form"><p class="help">${esc(notice)}</p><label>原因 *<textarea name="reason" maxlength="200" required></textarea></label><button type="submit">确认${esc(name)}</button></form>`);
  formHandler($('#reason-form'),async data=>{await callback(data.reason);modal.close();await route();});
}
async function detailProduct(id) {
  const p=await api('/api/products/'+id);
  title('商品详情','查看当前内容与状态，历史交易以预约时的快照为准。');
  const owner=user.id===p.seller_id,admin=user.role==='ADMIN';
  const actions=[];
  if(owner&&['DRAFT','REJECTED','OFF','SALE'].includes(p.status)) actions.push(['edit','编辑商品']);
  if(owner&&['DRAFT','REJECTED','OFF'].includes(p.status)) actions.push(['submit','提交审核']);
  if(owner&&p.status==='PENDING') actions.push(['withdraw','撤回审核']);
  if(owner&&p.status==='SALE') actions.push(['take-down','主动下架']);
  if(owner&&p.status==='DRAFT') actions.push(['delete','删除草稿']);
  if(admin&&p.status==='PENDING') actions.push(['approve','审核通过'],['reject-review','驳回审核']);
  if(admin&&['PENDING','SALE','RESERVED','OFF','SOLD'].includes(p.status)) actions.push(['violation',p.status==='SOLD'?'追加违规备注':'违规处理']);
  content.innerHTML=`<section class="panel"><div class="detail-grid"><div><div class="product-image">${p.image_ids.length?`<img src="/images/${p.image_ids[0]}" alt="${esc(p.title)}">`:'拾光'}</div><div class="image-row">${p.image_ids.map(i=>`<a href="/images/${i}" target="_blank"><img src="/images/${i}" alt="商品图片"></a>`).join('')}</div></div><div>${badge(p.status)}<h2>${esc(p.title)}</h2><div class="metadata">${esc(p.category||'未分类')} / ${esc(p.condition||'未填写成色')}</div><div class="detail-price">¥ ${esc(p.price||'未定价')}</div><p>${esc(p.description||'卖家暂未填写描述。')}</p><div class="metadata">卖家编号 <code>${p.seller_id}</code></div>${p.review_reason?`<div class="notice">审核原因：${esc(p.review_reason)}</div>`:''}<div class="actions">${actions.map(([a,l])=>`<button data-action="${a}" class="${['delete','violation','reject-review'].includes(a)?'danger':'secondary'}">${l}</button>`).join('')}</div>${!owner&&user.role==='USER'&&p.status==='SALE'?'<form id="reserve-form"><label>预约留言（双方可见） *<textarea name="message" maxlength="200" required placeholder="说明你的购买意向或约定交付方式"></textarea></label><button type="submit">提交预约</button></form>':''}${!user.id?'<div class="notice">登录后可预约他人在售商品。<a href="/login">去登录 →</a></div>':''}${p.active_reservation_id&&(owner||admin)?`<a class="button small" href="/reservation/${p.active_reservation_id}">查看当前预约</a>`:''}<p class="help">平台不提供在线付款，未认证用户校园身份。</p></div></div></section>${p.violations?.length?'<section class="panel"><h2>违规记录</h2>'+p.violations.map(v=>`<p>${dateText(v.created_at)} · ${esc(v.action)} · ${esc(v.reason)}</p>`).join('')+'</section>':''}`;
  if($('#reserve-form'))formHandler($('#reserve-form'),async data=>{
    const result=await command('/api/reservations',{product_id:id,message:data.message,expected_row_version:p.row_version,content_version:p.content_version});location.href='/reservation/'+result.object.id;
  });
  document.querySelectorAll('[data-action]').forEach(button=>button.onclick=async()=>{
    try{
      const action=button.dataset.action;
      if(action==='edit')return editProduct(p);
      const base={expected_row_version:p.row_version};
      if(action==='submit')base.content_version=p.content_version;
      if(action==='withdraw')base.batch_id=p.review_batch_id;
      if(action==='approve'||action==='reject-review'){
        const run=reason=>command(`/api/admin/products/${id}/review`,{...base,content_version:p.content_version,batch_id:p.review_batch_id,decision:action==='approve'?'APPROVE':'REJECT',reason});
        if(action==='reject-review')return reasonModal('驳回审核',run);
        await run('');
      }else if(action==='violation'){
        let reservationVersion=null;
        if(p.active_reservation_id)reservationVersion=(await api('/api/reservations/'+p.active_reservation_id)).row_version;
        return reasonModal(p.status==='SOLD'?'追加违规备注':'违规处理',reason=>command(`/api/admin/products/${id}/violation`,{...base,content_version:p.content_version,batch_id:p.review_batch_id,reason,expected_reservation_version:reservationVersion}),'未成交商品违规下架时会取消有效预约；已成交商品仅追加备注，不撤销完成状态。');
      }else if(action==='delete'){
        if(!confirm('仅从未提交且无历史的草稿可删除。确认删除？'))return;
        await command('/api/products/'+id,base,'DELETE');location.href='/my-products';return;
      }else await command(`/api/products/${id}/${action}`,base);
      await detailProduct(id);feedback('操作已保存',true);
    }catch(exc){feedback(exc.message);}
  });
}
async function listReservations(seller=false) {
  title(user.role==='ADMIN'?'预约核查':seller?'卖家工作台':'我的预约','查看预约进度与历史快照，私人留言仅在授权详情中展示。');
  content.innerHTML=`<form id="filters" class="panel filters"><label>预约状态<select name="status"><option value="">全部状态</option>${['PENDING','CONFIRMED','CANCELLED','REJECTED','COMPLETED'].map(s=>`<option value="${s}">${s==='PENDING'?'待确认':labels[s]}</option>`).join('')}</select></label><button type="submit">查询</button></form><div id="results"></div>`;
  activeLoader=async()=>{
    const params=new URLSearchParams(new FormData($('#filters')));params.set('scope',seller?'seller':'buyer');params.set('page',currentPage);
    const result=await api('/api/reservations?'+params);
    $('#results').innerHTML=result.items.length?`<div class="panel table-wrap"><table><thead><tr><th>预约商品</th><th>预约时标价</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody>${result.items.map(r=>`<tr><td>${esc(r.snapshot.title)}<br><small>${esc(r.snapshot.category)}</small></td><td>¥ ${r.snapshot.price}</td><td>${badge(r.status)}</td><td>${dateText(r.created_at)}</td><td><a href="/reservation/${r.id}">查看详情 →</a></td></tr>`).join('')}</tbody></table></div>`+pager(result.total):empty();bindPager();
  };formHandler($('#filters'),async()=>{currentPage=1;await activeLoader();});await activeLoader();
}
async function detailReservation(id) {
  const r=await api('/api/reservations/'+id);const s=r.snapshot;
  title('预约详情','历史商品内容固定保存，不随卖家后续编辑改变。');
  const seller=user.id===r.seller_id,buyer=user.id===r.buyer_id;
  const actions=[];
  if(seller&&r.status==='PENDING')actions.push(['confirm','确认预约'],['reject','拒绝预约']);
  if(seller&&r.status==='CONFIRMED')actions.push(['complete','标记完成']);
  if((buyer&&['PENDING','CONFIRMED'].includes(r.status))||(seller&&r.status==='CONFIRMED'))actions.push(['cancel','取消预约']);
  content.innerHTML=`<div class="panel">${badge(r.status)}<h2>${esc(s.title)}</h2><div class="metadata">${esc(s.category)} / ${esc(s.condition)} / 内容版本 ${s.content_version}</div><div class="detail-price">¥ ${s.price}</div><p>${esc(s.description)}</p><div class="image-row">${(s.image_ids||[]).map(i=>`<img src="/images/${i}" alt="预约快照图片">`).join('')}</div><p class="help">预约编号 ${id}<br>买家 ${r.buyer_id}<br>卖家 ${r.seller_id}<br>创建时间 ${dateText(r.created_at)}<br>完成时间 ${dateText(r.completed_at)}</p>${r.reason?`<div class="notice">处理原因：${esc(r.reason)}</div>`:''}<h3>预约留言</h3>${r.original_message!==undefined?`<div class="private-message">${esc(r.original_message)}</div>`:'<p class="help">管理员查看须选择核查场景、填写原因并成功保存访问记录。</p><button id="private-read" class="secondary">填写原因并查看留言</button><div id="private-output"></div>'}<div class="notice">${esc(r.notice)}</div><div class="actions">${actions.map(([a,l])=>`<button data-trade="${a}" class="${a==='cancel'||a==='reject'?'danger':''}">${l}</button>`).join('')}</div></div>`;
  document.querySelectorAll('[data-trade]').forEach(button=>button.onclick=async()=>{
    const action=button.dataset.trade;
    const run=reason=>command(`/api/reservations/${id}/${action}`,{expected_row_version:r.product_row_version,expected_reservation_version:r.row_version,...(reason?{reason}:{})});
    if(['reject','cancel'].includes(action))return reasonModal(button.textContent,run);
    if(action==='complete'&&!confirm('完成状态由卖家单方声明，不能回退。是否确认已完成线下交付？'))return;
    try{await run();await detailReservation(id);feedback('操作已保存',true);}catch(exc){feedback(exc.message);}
  });
  if($('#private-read'))$('#private-read').onclick=()=>{
    openModal('管理员私人留言访问',`<form id="private-form"><label>核查场景<select name="purpose"><option value="VIOLATION">违规核查</option><option value="STATE_CHECK">状态异常排查</option></select></label><label>查看原因 *<textarea name="reason" maxlength="200" required></textarea></label><button type="submit">留痕并查看</button></form>`);
    formHandler($('#private-form'),async data=>{const result=await api(`/api/admin/reservations/${id}/private-message-access`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});modal.close();$('#private-output').textContent=result.original_message;$('#private-output').className='private-message';});
  };
}
async function statistics() {
  title(user.role==='ADMIN'?'平台成交统计':'我的成交统计','统计仅包括已完成预约；金额取自预约时的商品快照。');
  content.innerHTML=`<form id="filters" class="panel filters"><label>开始日期<input name="from" type="date"></label><label>结束日期<input name="to" type="date"></label><label>分类<select name="category"><option value="">全部分类</option>${categoryOptions}</select></label><button type="submit">查询统计</button></form><div id="results"></div>`;
  activeLoader=async()=>{const params=new URLSearchParams(new FormData($('#filters')));params.set('page',currentPage);const r=await api('/api/statistics/completed?'+params);$('#results').innerHTML=`<div class="stat-grid"><div class="panel"><span class="muted">已标记完成的交易数量</span><div class="number">${r.count}<small> 笔</small></div></div><div class="panel"><span class="muted">已完成交易标价合计</span><div class="number">¥ ${r.total_price}</div></div></div><div class="notice">${r.notice}</div>`+(r.items.length?`<div class="panel table-wrap"><table><thead><tr><th>商品快照</th><th>分类</th><th>预约时标价</th><th>完成时间</th></tr></thead><tbody>${r.items.map(i=>`<tr><td><a href="/reservation/${i.reservation_id}">${esc(i.title)}</a></td><td>${esc(i.category)}</td><td>¥ ${i.price}</td><td>${dateText(i.completed_at)}</td></tr>`).join('')}</tbody></table></div>`:empty())+pager(r.count);bindPager();};
  formHandler($('#filters'),async()=>{currentPage=1;await activeLoader();});await activeLoader();
}
async function history() {
  const admin=user.role==='ADMIN';title(admin?'审计日志':'操作历史',admin?'只读操作元数据；日志不展示密码或完整私人留言。':'查看本人操作结果与状态变化。交易双方的预约进度请从预约详情查看。');
  content.innerHTML=`<form id="filters" class="panel filters"><label>开始日期<input type="date" name="from"></label><label>结束日期<input type="date" name="to"></label><label>操作类型<input name="action" placeholder="如 reservation.create"></label>${admin?'<label>操作者编号<input name="actor_id"></label>':''}<label>对象编号<input name="target_id"></label><button type="submit">查询</button></form><div id="results"></div>`;
  activeLoader=async()=>{const params=new URLSearchParams(new FormData($('#filters')));params.set('page',currentPage);const r=await api('/api/history?'+params);$('#results').innerHTML=r.items.length?`<div class="panel table-wrap"><table><thead><tr><th>时间</th><th>操作 / 对象</th>${admin?'<th>操作者</th>':''}<th>状态变化</th><th>结果</th></tr></thead><tbody>${r.items.map(i=>`<tr><td>${dateText(i.created_at)}</td><td>${esc(i.action)}<br><code>${esc(i.target_id)}</code></td>${admin?`<td><code>${esc(i.actor_id||'访客')}</code><br>${esc(i.role)}</td>`:''}<td>${esc(labels[i.before_state]||i.before_state||'—')} → ${esc(labels[i.after_state]||i.after_state||'—')}</td><td>${i.result==='SUCCESS'?'成功':'拒绝'}<br><small>${esc(i.failure_code)}</small></td></tr>`).join('')}</tbody></table></div>`+pager(r.total):empty();bindPager();};
  formHandler($('#filters'),async()=>{currentPage=1;await activeLoader();});await activeLoader();
}
async function loginPage() {
  title('欢迎来到拾光集市','从一件闲置好物开始，连接校园生活。');
  content.innerHTML=`<div class="login-grid"><form id="login-form" class="panel"><h2>登录账号</h2><p class="muted">普通用户与管理员使用同一登录入口。</p><label>用户名<input name="username" autocomplete="username" required></label><label>密码<input name="password" type="password" autocomplete="current-password" maxlength="64" required></label><button type="submit">登录</button></form><form id="register-form" class="panel"><h2>创建普通账号</h2><p class="muted">注册不代表已验证在校身份。</p><label>用户名<input name="username" pattern="[A-Za-z0-9_]{3,20}" required placeholder="3～20位英文字母、数字或下划线" autocomplete="username"></label><label>密码<input name="password" type="password" minlength="8" maxlength="64" required autocomplete="new-password" placeholder="8～64个字符"></label><label>昵称（可选）<input name="nickname" maxlength="40"></label><button type="submit" class="secondary">注册账号</button></form></div><p class="auth-note">请勿在预约留言中填写密码或其他认证秘密。</p>`;
  formHandler($('#login-form'),async data=>{await api('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});location.href='/market';});
  formHandler($('#register-form'),async(data,form)=>{await api('/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});feedback('注册成功，请使用左侧表单登录。',true);$('#login-form').elements.username.value=data.username;form.reset();});
}
async function route() {
  const path=location.pathname;
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.pathname===path||(path==='/'&&a.pathname==='/market')));
  if(!user.id&&!['/','/market','/login'].includes(path)&&!path.startsWith('/product/')){location.href='/login';return;}
  if(path==='/login')return loginPage();
  if(path.startsWith('/product/'))return detailProduct(path.split('/')[2]);
  if(path.startsWith('/reservation/'))return detailReservation(path.split('/')[2]);
  if(path==='/my-products')return listProducts('mine');
  if(path==='/admin')return listProducts('admin');
  if(path==='/my-reservations')return listReservations();
  if(path==='/seller-reservations')return listReservations(true);
  if(path==='/statistics')return statistics();
  if(path==='/history')return history();
  return listProducts('public');
}
$('#modal-close').onclick=()=>modal.close();
if($('#logout'))$('#logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'});location.href='/market';}catch(exc){feedback(exc.message);}};
route().catch(error=>{content.innerHTML=empty();feedback(error.message);});
