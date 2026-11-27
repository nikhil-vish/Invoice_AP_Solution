"use client";
import { Shell } from "@/components/Shell";
import { useCallback, useEffect, useState } from "react";
const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
type Metrics = { total_invoices_analysed:number; recommendations:Record<string,number>; human_decisions:Record<string,number>; comparison:Record<string,number>; override_rate:number|null; risk_distribution:Record<string,number>; common_findings:{category:string;count:number}[]; average_submission_to_decision_hours:number|null; operational:{total_invoices:number;statuses:Record<string,number>};financial:{total_invoice_value:string|null;total_taxable_value:string|null;cgst:string|null;sgst:string|null;igst:string|null} };
const rows=(data:Record<string,number>, keys:string[])=>keys.map(key=><p key={key} style={{margin:0,fontSize:12,color:"var(--muted)"}}>{key.replaceAll("_"," ")}: <strong style={{color:"var(--ink)"}}>{data[key]||0}</strong></p>);
export default function Home(){
  const [metrics,setMetrics]=useState<Metrics|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [filters,setFilters]=useState({date_from:"",date_to:"",risk_level:"",invoice_status:""});
  const load=useCallback(async()=>{
    try{
      const p=new URLSearchParams(Object.entries(filters).filter(([,v])=>v) as [string,string][]);
      const r=await fetch(`${API}/api/v1/invoices/dashboard/metrics?${p}`);
      if(!r.ok)throw new Error("Failed to load dashboard");
      setMetrics(await r.json());setError(null);
    }catch(e){setError(e instanceof Error?e.message:"Failed to load dashboard")}
  },[filters]);
  useEffect(()=>{load()},[load]);
  if(!metrics){
    return (
      <Shell>
        <header className="topbar"><div><div className="eyebrow">ACCOUNTS PAYABLE / INTELLIGENCE</div><h1>Overview</h1></div></header>
        <section className="intro"><div><div className="eyebrow light">AI INTELLIGENCE DASHBOARD</div><h2>Invoice review insights</h2><p>AI recommendations and human decisions are reported separately.</p></div><div className="introIcon">↗</div></section>
        <div className="filterBar">
          <input type="date" value={filters.date_from} suppressHydrationWarning onChange={e=>setFilters({...filters,date_from:e.target.value})} className="searchInput"/>
          <input type="date" value={filters.date_to} suppressHydrationWarning onChange={e=>setFilters({...filters,date_to:e.target.value})} className="searchInput"/>
          <select value={filters.risk_level} suppressHydrationWarning onChange={e=>setFilters({...filters,risk_level:e.target.value})} className="filterSelect"><option value="">All risk levels</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option></select>
          <input placeholder="Invoice status" value={filters.invoice_status} suppressHydrationWarning onChange={e=>setFilters({...filters,invoice_status:e.target.value})} className="searchInput"/>
        </div>
        <div className="emptyState"><div className="emptyIcon">↻</div><strong>Loading intelligence metrics…</strong></div>
      </Shell>
    );
  }
  const statusList=Object.entries(metrics.operational.statuses);
  const financial=metrics.financial;
  return (
    <Shell>
      <header className="topbar"><div><div className="eyebrow">ACCOUNTS PAYABLE / INTELLIGENCE</div><h1>Overview</h1></div></header>
      <section className="intro"><div><div className="eyebrow light">AI INTELLIGENCE DASHBOARD</div><h2>Invoice review insights</h2><p>AI recommendations and human decisions are reported separately.</p></div><div className="introIcon">↗</div></section>
      <div className="filterBar">
        <input type="date" value={filters.date_from} suppressHydrationWarning onChange={e=>setFilters({...filters,date_from:e.target.value})} className="searchInput"/>
        <input type="date" value={filters.date_to} suppressHydrationWarning onChange={e=>setFilters({...filters,date_to:e.target.value})} className="searchInput"/>
        <select value={filters.risk_level} suppressHydrationWarning onChange={e=>setFilters({...filters,risk_level:e.target.value})} className="filterSelect"><option value="">All risk levels</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option></select>
        <input placeholder="Invoice status" value={filters.invoice_status} suppressHydrationWarning onChange={e=>setFilters({...filters,invoice_status:e.target.value})} className="searchInput"/>
      </div>
      {error&&<div className="errorCard"><div className="errorIcon">!</div><strong>Failed to load intelligence metrics</strong><p>{error}</p></div>}
      <div className="metricGrid" style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))",gap:16,marginBottom:24}}>
        <div className="metricCard"><div className="metricLabel">Total invoices</div><div className="metricValue">{metrics.operational.total_invoices}</div><div className="metricSub">{statusList.map(([s,n])=>`${s}: ${n}`).join(" · ")||"No invoices"}</div></div>
        <div className="metricCard"><div className="metricLabel">Total invoice value</div><div className="metricValue">{financial.total_invoice_value===null?"—":`₹${financial.total_invoice_value}`}</div><div className="metricSub">All persisted invoices</div></div>
        <div className="metricCard"><div className="metricLabel">Invoices analysed by AI</div><div className="metricValue">{metrics.total_invoices_analysed}</div><div className="metricSub">Completed persisted analyses</div></div>
        <div className="metricCard"><div className="metricLabel">AI override rate</div><div className="metricValue">{metrics.override_rate===null?"—":`${metrics.override_rate}%`}</div><div className="metricSub">Paired final decisions only</div></div>
      </div>
      {metrics.total_invoices_analysed===0?(
        <div className="emptyState"><div className="emptyIcon">🤖</div><strong>No AI analysis data for these filters</strong><p style={{color:"var(--muted)",fontSize:12,marginTop:6}}>Metrics appear after completed AI analysis.</p></div>
      ):(
        <div className="reviewGrid">
          <section className="reviewPanel aiPanel"><h3>AI recommendations</h3>{rows(metrics.recommendations,["APPROVE","REJECT","REQUEST_CLARIFICATION"])}</section>
          <section className="reviewPanel aiPanel"><h3>Human decisions</h3>{rows(metrics.human_decisions,["APPROVED","REJECTED"])}</section>
          <section className="reviewPanel aiPanel"><h3>Risk distribution</h3>{rows(metrics.risk_distribution,["LOW","MEDIUM","HIGH"])}</section>
          <section className="reviewPanel aiPanel"><h3>AI vs final human decision</h3>{Object.keys(metrics.comparison).length?rows(metrics.comparison,Object.keys(metrics.comparison)):<p className="muted">No paired decisions yet.</p>}</section>
          <section className="reviewPanel aiPanel full"><h3>Common exceptions and anomalies</h3>{metrics.common_findings.length?metrics.common_findings.map(x=><p key={x.category} style={{margin:0,fontSize:12,color:"var(--muted)"}}>{x.category.replaceAll("_"," ")}: <strong style={{color:"var(--ink)"}}>{x.count}</strong></p>):<p className="muted">No persisted findings.</p>}</section>
        </div>
      )}
    </Shell>
  );
}
