"use client";
import { Shell } from "@/components/Shell";
import { useState } from "react";
const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export default function CopilotPage(){
  const [q,setQ]=useState(""),[ans,setAns]=useState<string|null>(null),[loading,setLoading]=useState(false),[err,setErr]=useState<string|null>(null),[inv,setInv]=useState("");
  const ask=async()=>{setLoading(true);setErr(null);try{const token=localStorage.getItem("supabase_access_token")||"";const r=await fetch(`${API}/api/v1/invoices/copilot`,{method:"POST",headers:{"Content-Type":"application/json",...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({question:q,invoice_id:inv||undefined})});if(r.status===401){localStorage.removeItem("supabase_access_token");setErr("Session expired. Please sign in again.");return;}if(!r.ok)throw new Error(await r.text());const d=await r.json();setAns(d.answer)}catch(e){setErr(e instanceof Error?e.message:"Failed")}finally{setLoading(false)}};
  return <Shell><header className="topbar"><div><div className="eyebrow">AI COPILOT</div><h1>AP Copilot</h1></div></header>
  <div className="reviewPanel aiPanel" style={{padding:20,maxWidth:700}}>
    <div style={{display:"flex",gap:8,marginBottom:14,alignItems:"center"}}>
      <div className="aiIcon">✦</div><span style={{fontWeight:600,color:"var(--ink)",fontSize:14}}>Ask about invoices</span>
    </div>
    <input placeholder="Invoice ID (optional)" value={inv} onChange={e=>setInv(e.target.value)} className="inputField" style={{marginBottom:10}}/>
    <textarea value={q} onChange={e=>setQ(e.target.value)} rows={4} className="inputField" placeholder="Ask a question…" style={{resize:"vertical"}}/>
    <div style={{marginTop:10,display:"flex",gap:8}}>
      <button className="btnPrimary" onClick={ask} disabled={loading||!q.trim()}>{loading?"Thinking…":"Ask"}</button>
      <button className="btnOutline" onClick={()=>{setQ("");setAns(null);setInv("");}}>Clear</button>
    </div>
    {err&&<p style={{color:"var(--danger)",fontSize:12,marginTop:10}}>{err}</p>}
    {ans&&<div style={{marginTop:12,whiteSpace:"pre-wrap",fontSize:12,color:"var(--ink)",lineHeight:1.6}}>{ans}</div>}
  </div></Shell>;
}
