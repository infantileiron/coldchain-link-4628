import {state} from '../stores/session.js';import {esc} from '../utils/html.js';import {IDENTITY_LABELS,FIELD_LABELS} from '../constants/enums.js';
const sampleCode=id=>(state.samples.find(s=>s.id===id)||{}).code||('#'+id);
const srcSummary=i=>Object.entries(i.field_sources||{}).map(([f,sid])=>`${FIELD_LABELS[f]}←${esc(sampleCode(sid))}`).join('，');
export function render(){
 const sel=state.identitySel?state.identities.find(i=>i.id===state.identitySel):null;
 return `<div class=split><section class=panel>
 <h2>样本身份目录 / ${state.identities.length} 个实物</h2>
 <p>同一实物的多个编号归为一个身份；新研究每个身份只计一次。状态：独立身份 → 待核对 → 已合并 →（可拆回）。</p>
 <div class=scroll><table><thead><tr><th>状态</th><th>代表编号</th><th>温区</th><th>配对数</th><th>版本</th><th>暴露</th><th>超温</th><th>货损%</th><th>字段来源</th></tr></thead><tbody>
 ${state.identities.map(i=>`<tr class="${sel&&sel.id===i.id?'sel':''}" data-ident=${i.id} style=cursor:pointer>
 <td><span class="tag st-${esc(i.status)}">${IDENTITY_LABELS[i.status]||i.status}</span></td>
 <td>${esc(i.display_code)}</td><td>${esc(i.zone||'')}</td><td>${i.pair_count}</td><td>v${i.version}</td>
 <td>${i.exposure??'—'}</td><td>${i.excursions??'—'}</td><td>${i.loss??'—'}</td><td>${srcSummary(i)}</td></tr>`).join('')}
 </tbody></table></div>
 ${sel?detail(sel):'<p class=notice>点击上方行查看成员配对、逐项更正记录与拆回操作。</p>'}
 </section><aside class=side>
 <h2>归并工作台</h2>
 <form id=merge>
 <label>勾选疑似同一实物的样本（同温区）<small id=merge-zone></small></label>
 <div class=checklist>${state.samples.map(s=>`<label class=row><input type=checkbox name=samples value="${s.id}"> ${esc(s.code)} <small>（${esc((state.ships.find(sh=>sh.id===s.shipment_id)||{}).zone||'')}）</small></label>`).join('')}</div>
 <button type=button id=preview>预览冲突与配对</button>
 <div id=preview-box></div>
 <button class=primary id=merge-confirm disabled>确认归并并更正原记录</button>
 </form>
 ${sel&&sel.status==='merged'?splitBox(sel):''}
 </aside></div>`}
function detail(i){
 return `<h3>身份 #${i.id} · ${esc(i.display_code)} · 配对 ${i.pair_count} 条</h3>
 <div class=scroll><table><thead><tr><th>原记录编号</th><th>入组版本</th><th>离组版本</th></tr></thead><tbody>
 ${i.members.map(m=>`<tr><td>${esc(m.sample_code)}</td><td>v${m.joined_version}</td><td>${m.left_version?('v'+m.left_version):'在组'}</td></tr>`).join('')}
 </tbody></table></div>
 <h3>逐项更正（原值 → 新值 / 来源）</h3>
 ${i.corrections.length?`<div class=scroll><table><thead><tr><th>字段</th><th>原记录</th><th>原值</th><th>新值</th><th>来源编号</th><th>请求</th></tr></thead><tbody>
 ${i.corrections.map(c=>`<tr><td>${FIELD_LABELS[c.field]||c.field}</td><td>${esc(sampleCode(c.sample_id))}</td><td>${c.old_value??'空'}</td><td>${c.new_value}</td><td>${esc(c.source)}</td><td><small>${esc(c.request_id)}</small></td></tr>`).join('')}
 </tbody></table></div>`:'<p class=notice>该身份尚无更正记录。</p>'}`}
function splitBox(i){
 return `<h2>拆回身份 #${i.id}</h2><form id=split>
 <p>当前版本 v${i.version}；勾选拆回后仍保留在本身份的样本，其余恢复为独立身份。合并期间的更正原样保留，签核不自动恢复。</p>
 <div class=checklist>${i.active_sample_ids.map(sid=>`<label class=row><input type=checkbox name=retain value="${sid}" checked> ${esc(sampleCode(sid))}</label>`).join('')}</div>
 <input type=hidden name=identity_id value="${i.id}"><input type=hidden name=base_version value="${i.version}">
 <button class=primary>提交拆回</button></form>`}
export function previewHtml(preview,picked){
 const name=id=>esc(sampleCode(id));
 if(!preview.conflicts.length)return `<p class=notice>温区 ${esc(preview.zone||'')}：字段值一致，无冲突，可直接归并。</p>`;
 return preview.conflicts.map(c=>`<fieldset class=conflict><legend>${FIELD_LABELS[c.field]||c.field} 冲突（逐项选来源）</legend>
 ${c.values.map(v=>`<label class=row><input type=radio name="src-${c.field}" value="${v.sample_ids[0]}" ${picked[c.field]===v.sample_ids[0]?'checked':''}> ${name(v.sample_ids[0])} = ${v.value}</label>`).join('')}</fieldset>`).join('')}
