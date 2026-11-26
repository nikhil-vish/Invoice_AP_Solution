"use client";
import { Shell } from "@/components/Shell";
import { useState } from "react";
const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export default function CopilotPage(){
  const [q,setQ]=useState(""),[ans,setAns]=useState<string|null>(null),[loading,setLoading]=useState(false),[err,setErr]=useState<string|null>(null),[inv,setInv]=useState("");
  const ask=async()=>{setLoading(true);setErr(null);try{const token=localStorage.getItem("token")||"";const r=await fetch(`${API}/api/v1/invoices/copilot`,{method:"POST",headers:{"Content-Type":"application/json",...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({question:q,invoice_id:inv||undefined})});if(!r.ok)throw new Error(await r.text());const d=await r.json();setAns(d.answer)}catch(e){setErr(e instanceof Error?e.message:"Failed")}finally{setLoading(false)}};
  return <Shell><header className="topbar"><div><div className="eyebrow">AI COPILOT</div><h1>AP Copilot</h1></div></header>
  <div className="reviewPanel"><input placeholder="Invoice ID (optional)" value={inv} onChange={e=>setInv(e.target.value)} style={{width:"100%",marginBottom:8}}/>
  <textarea value={q} onChange={e=>setQ(e.target.value)} rows={4} style={{width:"100%"}} placeholder="Ask a question..."/>
  <button onClick={ask} disabled={loading||!q.trim()} style={{marginTop:8}}>{loading?"Thinking...":"Ask"}</button>
  {err&&<p style={{color:"red"}}>{err}</p>}
  {ans&&<div style={{marginTop:12,whiteSpace:"pre-wrap"}}>{ans}</div>}</div></Shell>;
}
