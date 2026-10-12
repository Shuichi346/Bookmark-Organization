import htmx from "htmx.org";
import "./style.css";
htmx.config.allowEval = false;
htmx.config.allowScriptTags = false;
htmx.config.includeIndicatorStyles = false;

type Node = {id:string;kind:string;name:string;parent:string;order:number};
type Endpoint = {runtime:string;base_url:string;model:string};
type Settings = {generation:Endpoint;embedding:Endpoint;openrouter_key_configured?:boolean;[key:string]:unknown};
const messages:Record<string,string> = JSON.parse(document.querySelector("#messages")!.textContent!);
const tree:Node[] = JSON.parse(document.querySelector("#tree-data")!.textContent!);
const settings:Settings = JSON.parse(document.querySelector("#settings-data")!.textContent!);
const csrf = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')!.content;
const project = document.querySelector<HTMLElement>(".workspace")!.dataset.project!;
const query = <T extends Element>(selector:string) => document.querySelector<T>(selector)!;
const t = (key:string) => messages[key] || messages.unknown_error;
const alertBox = query<HTMLElement>("#alert");
function showError(error:unknown) {
 alertBox.textContent=t(error instanceof Error ? error.message : "unknown_error");
 alertBox.hidden=false;
}
async function api(url:string, method:"POST"|"PUT"|"PATCH"="POST", data?:unknown) {
 const form=data instanceof FormData;
 const response=await fetch(url,{method,headers:{"X-CSRF-Token":csrf,...(form?{}:{"Content-Type":"application/json"})},body:data===undefined?undefined:form?data:JSON.stringify(data)});
 const result=await response.json();
 if (!response.ok) throw new Error(result.code || "unknown_error");
 return result;
}
async function safely(action:()=>Promise<void>) {
 alertBox.hidden=true;
 try {await action();} catch(error) {showError(error);}
}
query<HTMLSelectElement>("#language").addEventListener("change",event=>void safely(async()=>{
 await api("/api/language","POST",{preference:(event.target as HTMLSelectElement).value});
 location.reload();
}));
query<HTMLButtonElement>("#settings-toggle").addEventListener("click",()=>{
 const panel=query<HTMLElement>("#settings-panel");panel.hidden=!panel.hidden;
 query<HTMLElement>("#settings-toggle").setAttribute("aria-expanded",String(!panel.hidden));
 if(!panel.hidden) panel.scrollIntoView({block:"start"});
});
query<HTMLFormElement>("#import-form").addEventListener("submit",event=>{
 event.preventDefault();
 void safely(async()=>{
  const result=await api("/api/projects/import","POST",new FormData(event.target as HTMLFormElement));
  location.href="/?project="+encodeURIComponent(result.id);
 });
});
document.querySelector("#choose-file")?.addEventListener("click",()=>query<HTMLInputElement>("#html-file").click());

const checks=()=>Array.from(document.querySelectorAll<HTMLInputElement>(".folder-check"));
function normalized():string[] {
 const ids=new Set(checks().filter(c=>c.checked).map(c=>c.value));
 return tree.filter(n=>ids.has(n.id)).filter(n=>{
  let parent=n.parent;
  while(parent!=="root") {
   if(ids.has(parent)) return false;
   parent=tree.find(m=>m.id===parent)!.parent;
  }
  return true;
 }).sort((a,b)=>a.order-b.order).map(n=>n.id);
}
function updateScope() {
 const all=query<HTMLInputElement>("#scope-all").checked;
 const folders=normalized();
 const destination=query<HTMLSelectElement>("#destination");const previous=destination.value;
 destination.replaceChildren();
 if(all) destination.add(new Option(t("new_region"),"root"));
 else for(const id of folders) destination.add(new Option(tree.find(n=>n.id===id)!.name,id));
 if(Array.from(destination.options).some(o=>o.value===previous)) destination.value=previous;
 const targets=tree.filter(n=>{
  if(n.kind!=="bookmark") return false;
  if(all) return true;
  let parent=n.parent;
  while(parent!=="root"){
   if(folders.includes(parent)) return true;
   parent=tree.find(m=>m.id===parent)!.parent;
  }
  return false;
 });
 query<HTMLElement>("#selected-count").textContent=t("selected").replace("{count}",new Intl.NumberFormat(document.documentElement.lang).format(targets.length));
 sessionStorage.setItem("scope-"+project,JSON.stringify({all,folders:checks().filter(c=>c.checked).map(c=>c.value),destination:destination.value}));
}
if(project) {
 try {
  const saved=JSON.parse(sessionStorage.getItem("scope-"+project)||"null");
  if(saved){query<HTMLInputElement>("#scope-all").checked=saved.all;checks().forEach(c=>c.checked=saved.folders.includes(c.value)); updateScope(); if(Array.from(query<HTMLSelectElement>("#destination").options).some(o=>o.value===saved.destination)) query<HTMLSelectElement>("#destination").value=saved.destination;}
 } catch { /* A corrupt browser preference does not affect saved jobs. */ }
 updateScope();
 query<HTMLInputElement>("#scope-all").addEventListener("change",updateScope);
 checks().forEach(c=>c.addEventListener("change",()=>{query<HTMLInputElement>("#scope-all").checked=false;updateScope();}));
 query<HTMLSelectElement>("#destination").addEventListener("change",updateScope);
 query<HTMLFormElement>("#scope-form").addEventListener("submit",event=>{
  event.preventDefault();void safely(async()=>{
   const result=await api("/api/projects/"+project+"/jobs","POST",{all:query<HTMLInputElement>("#scope-all").checked,folders:normalized(),destination:query<HTMLSelectElement>("#destination").value,token:crypto.randomUUID()});
   const current=document.querySelector("#job-region");
   if(current) current.remove();
   location.href="/?project="+project+"&job="+result.id;
  });
 });
}
function formSettings():Settings {
 const form=query<HTMLFormElement>("#settings-form");const values=new FormData(form);
 const result=structuredClone(settings);
 for(const key of ["generation","embedding"] as const) {
  result[key]={runtime:String(values.get(key+".runtime")),base_url:String(values.get(key+".base_url")),model:String(values.get(key+".model")).trim()};
 }
 for(const [key,value] of values.entries()) if(!key.includes(".") && key!=="openrouter_api_key") result[key]=key==="rendering"?true:Number(value);
 result.openrouter_api_key=query<HTMLInputElement>("#openrouter-api-key").value.trim();
 const inference:Record<string,unknown>={
  source:query<HTMLSelectElement>("#inference-source").value,
  thinking:query<HTMLSelectElement>('select[name="inference.thinking"]').value==="on",
  temperature:Number(query<HTMLInputElement>('input[name="inference.temperature"]').value),
 };
 for(const key of ["top_k","top_p","min_p","repeat_penalty","presence_penalty"]) {
  inference[key]=query<HTMLInputElement>('input[name="enable.'+key+'"]').checked?Number(query<HTMLInputElement>('input[name="inference.'+key+'"]').value):null;
 }
 result.inference=inference;
 result.rendering=values.has("rendering");
 return result;
}
function updateInferenceControls() {
 query<HTMLFieldSetElement>("#inference-controls").disabled=query<HTMLSelectElement>("#inference-source").value!=="app";
 for(const key of ["top_k","top_p","min_p","repeat_penalty","presence_penalty"]) {
  query<HTMLInputElement>('input[name="inference.'+key+'"]').disabled=!query<HTMLInputElement>('input[name="enable.'+key+'"]').checked;
 }
}
query<HTMLSelectElement>("#inference-source").addEventListener("change",updateInferenceControls);
document.querySelectorAll<HTMLInputElement>('input[name^="enable."]').forEach(input=>input.addEventListener("change",updateInferenceControls));
updateInferenceControls();
const modelCandidates:Record<string,string[]>={generation:[settings.generation.model],embedding:[settings.embedding.model]};
function updateModelCandidates(key:string, filter=false) {
 const input=query<HTMLInputElement>('input[name="'+key+'.model"]');
 const select=query<HTMLSelectElement>("#"+key+"-models");
 const term=input.value.trim().toLowerCase();
 select.replaceChildren(new Option(t("choose_model"),""));
 for(const model of modelCandidates[key]) {
  if(!filter || model.toLowerCase().includes(term)) select.add(new Option(model,model));
 }
 if(modelCandidates[key].includes(input.value.trim())) select.value=input.value.trim();
}
for(const key of ["generation","embedding"]) {
 query<HTMLInputElement>('input[name="'+key+'.model"]').addEventListener("input",()=>updateModelCandidates(key,true));
 query<HTMLSelectElement>("#"+key+"-models").addEventListener("change",event=>{
  const model=(event.target as HTMLSelectElement).value;
  if(model) query<HTMLInputElement>('input[name="'+key+'.model"]').value=model;
 });
 updateModelCandidates(key);
}
function updateProviders() {
 const openrouter=["generation","embedding"].some(key=>query<HTMLSelectElement>('select[name="'+key+'.runtime"]').value==="openrouter");
 query<HTMLElement>("#openrouter-settings").hidden=!openrouter;
 for(const key of ["generation","embedding"]) {
  query<HTMLInputElement>('input[name="'+key+'.base_url"]').readOnly=query<HTMLSelectElement>('select[name="'+key+'.runtime"]').value==="openrouter";
 }
}
document.querySelectorAll<HTMLSelectElement>('select[name$=".runtime"]').forEach(select=>select.addEventListener("change",()=>{
 const key=select.name.split(".")[0];
 const urls:Record<string,string>={lmstudio:"http://localhost:1234/v1",ollama:"http://localhost:11434/v1",openrouter:"https://openrouter.ai/api/v1"};
 query<HTMLInputElement>('input[name="'+key+'.base_url"]').value=urls[select.value];
 query<HTMLInputElement>('input[name="'+key+'.model"]').value="";
 modelCandidates[key]=[];
 updateModelCandidates(key);
 query<HTMLElement>("#settings-feedback").textContent="";
 updateProviders();
}));
updateProviders();
query<HTMLButtonElement>("#probe").addEventListener("click",()=>void safely(async()=>{
 const result=await api("/api/settings/probe","POST",formSettings());
 for(const key of ["generation","embedding"]) {
  modelCandidates[key]=result[key];
  updateModelCandidates(key);
 }
 query<HTMLElement>("#settings-feedback").textContent=t("connected");
}));
query<HTMLFormElement>("#settings-form").addEventListener("submit",event=>{
 event.preventDefault();void safely(async()=>{
  const saved=await api("/api/settings","PUT",formSettings());
  Object.assign(settings,saved);
  query<HTMLInputElement>("#openrouter-api-key").value="";
  query<HTMLElement>("#openrouter-key-help").textContent=t(saved.openrouter_key_configured?"openrouter_key_saved":"openrouter_key_help");
  query<HTMLElement>("#settings-feedback").textContent=t("saved");
 });
});
document.body.addEventListener("click",event=>{
 const button=(event.target as Element).closest<HTMLButtonElement>("button[data-action]");
 if(!button) return;
 void safely(async()=>{
  const job=button.closest<HTMLElement>("[data-job]")!.dataset.job;
  const action=button.dataset.action;
  const result=await api("/api/jobs/"+job+"/"+action,"POST",action==="proposal"?{allow_incomplete:document.querySelector<HTMLInputElement>("#allow-incomplete")?.checked}:undefined);
  if(action==="proposal") location.href="/?project="+project+"&proposal="+result.id;
  else htmx.trigger(query("#job-region"),"refresh");
 });
});
let page=1;
async function refreshComparison() {
 const section=document.querySelector<HTMLElement>("#proposal-section");if(!section)return;
 const params=new URLSearchParams({q:query<HTMLInputElement>("#search").value,status:query<HTMLSelectElement>("#status-filter").value,page:String(page)});
 await htmx.ajax("get","/ui/proposals/"+section.dataset.proposal+"?"+params,{target:"#comparison",swap:"innerHTML"});
}
document.querySelector("#search")?.addEventListener("input",()=>{page=1;void refreshComparison().catch(showError);});
document.querySelector("#status-filter")?.addEventListener("change",()=>{page=1;void refreshComparison().catch(showError);});
document.body.addEventListener("click",event=>{
 const target=(event.target as Element).closest<HTMLButtonElement>("button");
 if(target?.dataset.page) {page=Number(target.dataset.page);void refreshComparison().catch(showError);}
 if(target?.classList.contains("save-item")) void safely(async()=>{
  const section=query<HTMLElement>("#proposal-section");const row=target.closest<HTMLElement>("tr")!;
  const result=await api("/api/proposals/"+section.dataset.proposal+"/items/"+row.dataset.bookmark,"PATCH",{name:row.querySelector<HTMLInputElement>(".edit-name")!.value,parent:row.querySelector<HTMLSelectElement>(".edit-parent")!.value});
  section.dataset.proposal=result.id;query<HTMLAnchorElement>("#export").href="/api/proposals/"+result.id+"/export";
  history.replaceState(null,"","/?project="+project+"&proposal="+result.id);
  await refreshComparison();
 });
});
document.body.addEventListener("htmx:responseError",()=>showError(new Error("unknown_error")));
document.body.addEventListener("htmx:configRequest",event=>{
 (event as CustomEvent).detail.headers["X-CSRF-Token"]=csrf;
});
