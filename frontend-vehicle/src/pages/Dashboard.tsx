/**
 * CVIS v5.0 — Cognitive Vehicle Intelligence System
 * Dashboard (production-final, fully upgraded)
 *
 * New panels added:
 *  1. Future Risk Prediction   — trend / predicted risk / time-to-failure
 *  2. Ensemble Transparency    — per-model scores + disagreement
 *  3. Uncertainty / Trust      — confidence / disagreement / diversity
 *  4. Memory / Trend           — anomaly history sparkline + trend arrow
 *  5. System Mode Banner       — NORMAL / WARNING / CRITICAL / DEGRADED
 *  6. Action Impact            — why the current action matters
 *  7. Audio alert              — beep on CRITICAL (already present, improved)
 *  8. Camera overlay           — risk-coloured boxes + TTC labels (already present)
 *  9. System Health Score      — composite of latency + confidence + sensors
 */

import {
  useEffect, useRef, useState, useCallback, useMemo
} from "react";
import {
  AreaChart, Area, ResponsiveContainer, XAxis, YAxis,
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  BarChart, Bar, Cell, Tooltip,
} from "recharts";

/* ─── THEME ─────────────────────────────────────────────────── */
const T = {
  bg:"#020306", surface:"rgba(3,6,16,0.82)", border:"rgba(0,200,255,0.12)",
  amber:"#e8a800", amberGlow:"rgba(232,168,0,0.3)",
  cyan:"#00c8ff",  cyanGlow:"rgba(0,200,255,0.25)",
  success:"#00e87a", warning:"#ff9500", danger:"#ff1e40",
  text:"#c0d8f0", muted:"#3a5878", purple:"#a855f7",
};

/* ─── STYLES ─────────────────────────────────────────────────── */
const STYLES = `
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=IBM+Plex+Mono:wght@300;400;500&display=swap');
@keyframes pulse     { 0%,100%{opacity:1}50%{opacity:0.4} }
@keyframes slideIn   { from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)} }
@keyframes glow      { 0%,100%{box-shadow:0 0 20px rgba(0,200,255,0.15)}50%{box-shadow:0 0 40px rgba(0,200,255,0.4)} }
@keyframes critFlash { 0%,100%{box-shadow:0 0 30px rgba(255,30,64,0.35)}50%{box-shadow:0 0 70px rgba(255,30,64,0.75)} }
@keyframes radarSpin { from{transform:rotate(0deg)}to{transform:rotate(360deg)} }
@keyframes scanV     { 0%{top:-4%}100%{top:104%} }
@keyframes blink     { 0%,49%{opacity:1}50%,100%{opacity:0} }
@keyframes logSlide  { from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:translateX(0)} }
@keyframes ttcPulse  { 0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.6;transform:scale(1.05)} }
@keyframes modeSlide { from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)} }
* { box-sizing:border-box; margin:0; padding:0; }
::-webkit-scrollbar { width:3px; }
::-webkit-scrollbar-thumb { background:rgba(0,200,255,0.2); border-radius:2px; }
button { outline:none; cursor:pointer; }
input[type=range] {
  -webkit-appearance:none; width:100%; height:4px;
  background:rgba(0,200,255,0.15); border-radius:2px; outline:none; cursor:pointer;
}
input[type=range]::-webkit-slider-thumb {
  -webkit-appearance:none; width:14px; height:14px; border-radius:50%;
  background:#00c8ff; box-shadow:0 0 8px #00c8ff; cursor:pointer;
}
.sim-btn { padding:8px 6px; border-radius:5px; font-size:8px; font-family:'Orbitron',monospace;
  font-weight:700; letter-spacing:0.06em; border:1px solid; transition:all 0.2s; }
.sim-btn:hover { transform:translateY(-1px); filter:brightness(1.3); }
`;

/* ═══════════════════════════════════════════════════════════════
   WATCHDOG
═══════════════════════════════════════════════════════════════ */
function useWatchdog(lastFrameTs, pipelineMs) {
  const [watchdogState, setWatchdogState] = useState("OK");
  useEffect(() => {
    const id = setInterval(() => {
      const age = Date.now() - lastFrameTs;
      if (age > 3000)         setWatchdogState("STALE");
      else if (pipelineMs > 200) setWatchdogState("SLOW");
      else                    setWatchdogState("OK");
    }, 500);
    return () => clearInterval(id);
  }, [lastFrameTs, pipelineMs]);
  return watchdogState;
}

/* ═══════════════════════════════════════════════════════════════
   VALIDATION ENGINE
═══════════════════════════════════════════════════════════════ */
class ValidationTracker {
  constructor() { this.tp=0;this.fp=0;this.tn=0;this.fn=0;this.log=[];this.hysteresis_holds=0;this.hysteresis_total=0; }
  record(decision,hazard,hysteresisHeld) {
    const alarmed=(decision?.action!=="MAINTAIN"),realDanger=(hazard??0)>0.4;
    if(alarmed&&realDanger)this.tp++;else if(alarmed&&!realDanger)this.fp++;
    else if(!alarmed&&!realDanger)this.tn++;else this.fn++;
    this.hysteresis_total++;
    if(hysteresisHeld)this.hysteresis_holds++;
    this.log.push({ts:Date.now(),action:decision?.action,score:decision?.composite_score,hazard});
    if(this.log.length>200)this.log.shift();
  }
  metrics() {
    const total=this.tp+this.fp+this.tn+this.fn||1;
    const prec=this.tp/(this.tp+this.fp+0.001),rec=this.tp/(this.tp+this.fn+0.001);
    const f1=2*(prec*rec)/(prec+rec+0.001);
    const stab=this.hysteresis_total>0?(this.hysteresis_holds/this.hysteresis_total*100):0;
    return {tp:this.tp,fp:this.fp,tn:this.tn,fn:this.fn,precision:prec*100,recall:rec*100,f1:f1*100,fpRate:this.fp/total*100,stability:stab,total:this.log.length};
  }
}

function exportDataset(frames) {
  if(!frames.length)return;
  const lines=frames.map(f=>JSON.stringify({ts:f.timestamp,features:f.perception?.features??{},signals:f.perception?.signals??{},anomaly:f.anomaly?.score,hazard:f.risk?.hazard,decision:f.decision?.action,confidence:f.decision?.confidence,composite:f.decision?.composite_score,outcome:f.risk?.level}));
  const blob=new Blob([lines.join("\n")],{type:"application/jsonl"});
  const url=URL.createObjectURL(blob);
  const a=document.createElement("a");a.href=url;a.download=`cvis_dataset_${Date.now()}.jsonl`;a.click();URL.revokeObjectURL(url);
}

function roundRect(ctx,x,y,w,h,r=4){ctx.beginPath();ctx.moveTo(x+r,y);ctx.lineTo(x+w-r,y);ctx.quadraticCurveTo(x+w,y,x+w,y+r);ctx.lineTo(x+w,y+h-r);ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);ctx.lineTo(x+r,y+h);ctx.quadraticCurveTo(x,y+h,x,y+h-r);ctx.lineTo(x,y+r);ctx.quadraticCurveTo(x,y,x+r,y);ctx.closePath();ctx.fill();}

/* ─── Primitives ─────────────────────────────────────────────── */
const Sec = ({title,children,alert,accent,compact,badge}) => (
  <div style={{backdropFilter:"blur(22px)",background:T.surface,padding:compact?"13px 15px":"16px 18px",borderRadius:"6px",border:`1px solid ${alert?`${T.danger}50`:accent?`${accent}25`:T.border}`,boxShadow:alert?`0 0 28px ${T.danger}12`:"0 4px 24px rgba(0,0,0,0.35)",animation:"slideIn 0.5s ease-out"}}>
    {title&&(<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:compact?"9px":"13px"}}>
      <div style={{fontSize:"9px",fontWeight:500,fontFamily:"'IBM Plex Mono',monospace",color:accent||T.cyan,letterSpacing:"0.14em",textTransform:"uppercase"}}>▸ {title}</div>
      <div style={{display:"flex",gap:"6px",alignItems:"center"}}>
        {badge&&<div style={{fontSize:"8px",padding:"2px 7px",borderRadius:"3px",background:`${badge.color}15`,border:`1px solid ${badge.color}40`,color:badge.color,fontFamily:"'IBM Plex Mono',monospace"}}>{badge.text}</div>}
        {alert&&<div style={{fontSize:"9px",color:T.danger,fontFamily:"'IBM Plex Mono',monospace",animation:"blink 1s infinite"}}>● ALERT</div>}
      </div>
    </div>)}
    {children}
  </div>
);

const SensorBar = ({label,value,max=100,unit="%",color,threshold}) => {
  const pct=Math.min(100,(value/max)*100),c=(threshold&&value>threshold)?T.danger:color;
  return(<div style={{marginBottom:"9px"}}>
    <div style={{display:"flex",justifyContent:"space-between",fontSize:"10px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
      <span style={{color:T.muted}}>{label}</span>
      <span style={{color:c,fontWeight:500}}>{typeof value==="number"?value.toFixed(1):value}{unit}</span>
    </div>
    <div style={{height:"5px",borderRadius:"2px",background:"rgba(0,0,0,0.5)",overflow:"hidden",position:"relative"}}>
      <div style={{width:`${pct}%`,height:"100%",background:`linear-gradient(90deg,${c}99,${c})`,boxShadow:`0 0 8px ${c}80`,transition:"width 0.6s ease",borderRadius:"2px"}}/>
      {threshold&&<div style={{position:"absolute",top:0,left:`${(threshold/max)*100}%`,width:"1px",height:"100%",background:`${T.warning}80`}}/>}
    </div>
  </div>);
};

const CircleGauge = ({value,max=100,label,color,size=80,unit="%"}) => {
  const r=size/2-9,C=2*Math.PI*r,arc=C*0.75,filled=(Math.min(value??0,max)/max)*arc,cx=size/2,cy=size/2;
  return(<svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{overflow:"visible"}}>
    <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(0,0,0,0.5)" strokeWidth="6" strokeDasharray={`${arc} ${C}`} transform={`rotate(135 ${cx} ${cy})`} strokeLinecap="round"/>
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="6" strokeDasharray={`${filled} ${C}`} transform={`rotate(135 ${cx} ${cy})`} strokeLinecap="round" style={{filter:`drop-shadow(0 0 5px ${color})`,transition:"stroke-dasharray 0.8s ease"}}/>
    <text x={cx} y={cy-4} textAnchor="middle" fill={color} fontSize="15" fontWeight="700" fontFamily="Orbitron,monospace">{typeof value==="number"?value.toFixed(0):value}</text>
    <text x={cx} y={cy+10} textAnchor="middle" fill="rgba(150,180,200,0.5)" fontSize="7" fontFamily="IBM Plex Mono,monospace">{unit}</text>
    <text x={cx} y={cy+21} textAnchor="middle" fill="rgba(100,140,170,0.4)" fontSize="6.5" fontFamily="IBM Plex Mono,monospace" letterSpacing="0.06em">{label}</text>
  </svg>);
};

const Advisory = ({text,sev="INFO",idx=0}) => {
  const c=sev==="CRITICAL"?T.danger:sev==="WARNING"?T.warning:sev==="CAUTION"?T.amber:T.cyan;
  return(<div style={{padding:"8px 11px",borderRadius:"4px",background:`${c}08`,borderLeft:`2px solid ${c}`,fontSize:"10px",color:T.text,fontFamily:"'IBM Plex Mono',monospace",animation:`slideIn ${0.3+idx*0.07}s ease-out`,marginBottom:"6px",lineHeight:"1.55"}}>
    <span style={{color:c,marginRight:"6px",fontSize:"9px"}}>{({CRITICAL:"⬛",WARNING:"▲",CAUTION:"◆",INFO:"◈"})[sev]||"◈"}</span>
    <span style={{color:c,fontWeight:500,marginRight:"5px",fontSize:"8px",letterSpacing:"0.08em"}}>{sev}</span>
    <span style={{color:T.text}}>{text}</span>
  </div>);
};

/* ─── Road Background ────────────────────────────────────────── */
const RoadBg = ({isCritical}) => {
  const cvs=useRef(null),raf=useRef(null);
  useEffect(()=>{
    const canvas=cvs.current;if(!canvas)return;
    const ctx=canvas.getContext("2d");
    const resize=()=>{canvas.width=window.innerWidth;canvas.height=window.innerHeight;};
    resize();window.addEventListener("resize",resize);
    const stars=Array.from({length:140},()=>({x:Math.random(),y:Math.random()*0.4,r:0.4+Math.random()*1.2,b:0.3+Math.random()*0.7}));
    const cityL=Array.from({length:55},(_,i)=>({x:i/55,h:4+Math.random()*18,w:1+Math.random()*3,color:Math.random()>0.5?"0,200,255":"255,180,0",f:0.7+Math.random()*0.3}));
    const draw=t=>{
      const W=canvas.width,H=canvas.height;ctx.clearRect(0,0,W,H);
      const sky=ctx.createLinearGradient(0,0,0,H*0.44);sky.addColorStop(0,"#010104");sky.addColorStop(0.65,"#020614");sky.addColorStop(1,"#030a1c");ctx.fillStyle=sky;ctx.fillRect(0,0,W,H);
      stars.forEach(s=>{const f=s.b*(0.6+0.4*Math.sin(t*0.001*s.b+s.x*20));ctx.beginPath();ctx.arc(s.x*W,s.y*H,s.r,0,Math.PI*2);ctx.fillStyle=`rgba(180,220,255,${f})`;ctx.fill();});
      const hz=H*0.4;
      cityL.forEach(l=>{const fl=l.f*(0.85+0.15*Math.sin(t*0.002+l.x*50));ctx.fillStyle=`rgba(${l.color},${0.35*fl})`;ctx.fillRect(l.x*W,hz-l.h,l.w,l.h);});
      const vpX=W/2,vpY=hz,lT=vpX-W*0.065,lB=W*0.08,rT=vpX+W*0.065,rB=W*0.92;
      const rs=ctx.createLinearGradient(0,vpY,0,H);rs.addColorStop(0,"#07080e");rs.addColorStop(0.25,"#0d0f16");rs.addColorStop(1,"#12151f");ctx.fillStyle=rs;ctx.beginPath();ctx.moveTo(lT,vpY);ctx.lineTo(rT,vpY);ctx.lineTo(rB,H);ctx.lineTo(lB,H);ctx.closePath();ctx.fill();
      const lp=p=>({lx:lT+(lB-lT)*p,rx:rT+(rB-rT)*p,y:vpY+(H-vpY)*p});
      const dp=(t*0.00025)%1;
      for(let d=0;d<14;d++){const prog=((d/14)+dp)%1,pA=lp(prog),pB=lp(Math.min(1,((d/14)+dp+0.045)%1));ctx.beginPath();ctx.moveTo((pA.lx+pA.rx)/2,pA.y);ctx.lineTo((pB.lx+pB.rx)/2,pB.y);ctx.strokeStyle=`rgba(255,255,255,${0.2+prog*0.55})`;ctx.lineWidth=1+prog*3;ctx.stroke();}
      const vg=ctx.createLinearGradient(0,H*0.78,0,H);vg.addColorStop(0,"transparent");vg.addColorStop(0.35,"rgba(3,6,16,0.65)");vg.addColorStop(1,"rgba(3,6,16,0.97)");ctx.fillStyle=vg;ctx.fillRect(0,H*0.78,W,H*0.22);
      if(isCritical){const al=0.06+Math.sin(t*0.006)*0.04;const cv=ctx.createRadialGradient(W/2,H/2,W*0.2,W/2,H/2,W*0.9);cv.addColorStop(0,"transparent");cv.addColorStop(1,`rgba(255,20,50,${al})`);ctx.fillStyle=cv;ctx.fillRect(0,0,W,H);}
      raf.current=requestAnimationFrame(draw);
    };
    raf.current=requestAnimationFrame(draw);
    return()=>{cancelAnimationFrame(raf.current);window.removeEventListener("resize",resize);};
  },[isCritical]);
  return <canvas ref={cvs} style={{position:"fixed",top:0,left:0,width:"100%",height:"100%",zIndex:0,pointerEvents:"none"}}/>;
};

/* ─── Hazard Orb ─────────────────────────────────────────────── */
const HazardOrb = ({hazard,dangerLevel,color}) => {
  const isCrit=dangerLevel==="CRITICAL";
  return(<div style={{display:"flex",flexDirection:"column",alignItems:"center",padding:"6px 0 2px"}}>
    <div style={{position:"relative",display:"flex",alignItems:"center",justifyContent:"center"}}>
      <div style={{position:"absolute",width:"178px",height:"178px",borderRadius:"50%",border:`1px solid ${color}20`,animation:isCrit?"critFlash 1s infinite":"glow 3s infinite"}}/>
      <div style={{position:"absolute",width:"158px",height:"158px",borderRadius:"50%",border:`1px dashed ${color}18`}}>
        {[0,120,240].map((deg,i)=><div key={i} style={{position:"absolute",top:"50%",left:"50%",width:"7px",height:"7px",borderRadius:"50%",marginLeft:"-3.5px",marginTop:"-3.5px",background:color,boxShadow:`0 0 8px ${color}`,animation:`radarSpin ${3+i}s linear infinite`,transformOrigin:"3.5px 3.5px",transform:`rotate(${deg}deg) translateX(79px) rotate(-${deg}deg)`}}/>)}
      </div>
      <div style={{width:"128px",height:"128px",borderRadius:"50%",background:`radial-gradient(circle at 38% 35%,${color}28 0%,${color}10 45%,transparent 70%)`,border:`1.5px solid ${color}60`,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",backdropFilter:"blur(10px)",boxShadow:`0 0 50px ${color}35,inset 0 0 28px ${color}08`,position:"relative",zIndex:1}}>
        <div style={{fontSize:"28px",fontWeight:900,color,fontFamily:"'Orbitron',monospace",textShadow:`0 0 15px ${color}`,lineHeight:1}}>{((hazard??0)*100).toFixed(0)}%</div>
        <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",letterSpacing:"0.12em",marginTop:"2px"}}>HAZARD RISK</div>
        <div style={{fontSize:"9px",color,fontFamily:"'Orbitron',monospace",fontWeight:700,marginTop:"3px"}}>{dangerLevel}</div>
      </div>
      <svg width="158" height="158" style={{position:"absolute",top:"10px",left:"10px"}}>
        <circle cx="79" cy="79" r="71" fill="none" stroke={`${color}10`} strokeWidth="2"/>
        <circle cx="79" cy="79" r="71" fill="none" stroke={color} strokeWidth="2" strokeDasharray={`${(hazard??0)*446} 446`} strokeDashoffset="112" strokeLinecap="round" style={{filter:`drop-shadow(0 0 3px ${color})`,transition:"stroke-dasharray 1s ease"}}/>
      </svg>
    </div>
    <div style={{marginTop:"7px",fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",color:T.muted,letterSpacing:"0.1em"}}>
      {isCrit?"⚠ IMMEDIATE ACTION REQUIRED":dangerLevel==="WARNING"?"⚠ ELEVATED RISK DETECTED":"✓ ALL SYSTEMS NOMINAL"}
    </div>
  </div>);
};

/* ─── Proximity Radar ────────────────────────────────────────── */
const ProximityRadar = ({hazard,objects=[]}) => {
  const cvs=useRef(null),rafR=useRef(null);
  useEffect(()=>{
    const canvas=cvs.current;if(!canvas)return;
    const ctx=canvas.getContext("2d"),S=130;canvas.width=S;canvas.height=S;
    const cx=S/2,cy=S/2,maxR=S/2-6;let angle=0;
    const draw=()=>{
      ctx.clearRect(0,0,S,S);
      ctx.beginPath();ctx.arc(cx,cy,maxR,0,Math.PI*2);ctx.fillStyle="rgba(0,10,25,0.9)";ctx.fill();
      [0.33,0.66,1].forEach(f=>{ctx.beginPath();ctx.arc(cx,cy,maxR*f,0,Math.PI*2);ctx.strokeStyle="rgba(0,200,255,0.1)";ctx.lineWidth=0.7;ctx.stroke();});
      ctx.save();ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,maxR,angle-1.2,angle);ctx.closePath();ctx.fillStyle="rgba(0,200,255,0.05)";ctx.fill();ctx.restore();
      const sc=hazard>0.7?"#ff1e40":"#00c8ff";
      ctx.save();ctx.translate(cx,cy);ctx.rotate(angle);ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(0,-maxR);ctx.strokeStyle=sc;ctx.lineWidth=1.5;ctx.shadowColor=sc;ctx.shadowBlur=6;ctx.stroke();ctx.restore();
      const showObjs=objects.length>0?objects.slice(0,4).map((o,i)=>({dist:Math.min(1,(o.distance??15)/25),bearing:-0.3+i*0.5,size:3.5,label:o.label||"VEH"})):[{dist:0.45,bearing:-0.3,size:3.5,label:"VEH"},{dist:0.72,bearing:0.8,size:2.5,label:"OBJ"},{dist:0.28,bearing:-1.1,size:4,label:"VEH"}];
      showObjs.forEach(o=>{const a=angle+o.bearing-Math.PI/2,ox=cx+Math.cos(a)*maxR*o.dist,oy=cy+Math.sin(a)*maxR*o.dist;ctx.beginPath();ctx.arc(ox,oy,o.size,0,Math.PI*2);ctx.fillStyle=hazard>0.6?"rgba(255,100,0,0.8)":"rgba(0,230,120,0.8)";ctx.shadowColor=hazard>0.6?"#ff6400":"#00e878";ctx.shadowBlur=8;ctx.fill();ctx.shadowBlur=0;ctx.fillStyle="rgba(180,220,255,0.6)";ctx.font="6px IBM Plex Mono";ctx.fillText(o.label,ox+5,oy-4);});
      ctx.beginPath();ctx.arc(cx,cy,4,0,Math.PI*2);ctx.fillStyle="#00c8ff";ctx.shadowColor="#00c8ff";ctx.shadowBlur=8;ctx.fill();ctx.shadowBlur=0;
      angle+=0.03;rafR.current=requestAnimationFrame(draw);
    };
    draw();return()=>cancelAnimationFrame(rafR.current);
  },[hazard,objects.length]);
  return <canvas ref={cvs} style={{width:"130px",height:"130px",display:"block"}}/>;
};

/* ═══════════════════════════════════════════════════════════════
   NEW: SYSTEM MODE BANNER
═══════════════════════════════════════════════════════════════ */
const SystemModeBanner = ({dangerLevel,watchdogState,systemHealth,failsafe}) => {
  const isDegrade = watchdogState!=="OK"||failsafe==="DEGRADED"||failsafe==="SAFE_MODE";
  const mode = dangerLevel==="CRITICAL"?"CRITICAL":isDegrade?"DEGRADED":dangerLevel==="WARNING"?"WARNING":"NORMAL";
  const cfg = {
    CRITICAL: {c:T.danger,  msg:"AUTONOMOUS INTERVENTION ACTIVE — COLLISION RISK DETECTED", anim:"critFlash 1s infinite"},
    DEGRADED: {c:T.warning, msg:"DEGRADED MODE — Sensor dropout or latency over budget", anim:"blink 2s infinite"},
    WARNING:  {c:T.amber,   msg:"ELEVATED RISK — Enhanced monitoring engaged", anim:"none"},
    NORMAL:   {c:T.success, msg:"ALL SYSTEMS NOMINAL — Cognitive pipeline running", anim:"none"},
  }[mode];
  return(
    <div style={{padding:"8px 18px",marginBottom:"10px",borderRadius:"5px",background:`${cfg.c}10`,border:`1px solid ${cfg.c}45`,display:"flex",justifyContent:"space-between",alignItems:"center",animation:"modeSlide 0.4s ease-out",boxShadow:mode==="CRITICAL"?`0 0 30px ${cfg.c}25`:"none"}}>
      <div style={{display:"flex",alignItems:"center",gap:"12px"}}>
        <div style={{width:"8px",height:"8px",borderRadius:"50%",background:cfg.c,animation:cfg.anim}}/>
        <div>
          <span style={{fontSize:"10px",fontFamily:"'Orbitron',monospace",fontWeight:700,color:cfg.c,letterSpacing:"0.1em",marginRight:"14px"}}>MODE: {mode}</span>
          <span style={{fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",color:T.text}}>{cfg.msg}</span>
        </div>
      </div>
      <div style={{display:"flex",alignItems:"center",gap:"14px"}}>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>SYSTEM HEALTH</div>
          <div style={{fontSize:"14px",fontFamily:"'Orbitron',monospace",fontWeight:700,color:systemHealth>75?T.success:systemHealth>50?T.warning:T.danger}}>{systemHealth.toFixed(0)}%</div>
        </div>
        <div style={{width:"50px",height:"6px",borderRadius:"3px",background:"rgba(0,0,0,0.4)",overflow:"hidden"}}>
          <div style={{width:`${systemHealth}%`,height:"100%",background:systemHealth>75?T.success:systemHealth>50?T.warning:T.danger,transition:"width 0.8s ease"}}/>
        </div>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   NEW: FUTURE RISK PREDICTION PANEL
═══════════════════════════════════════════════════════════════ */
const FutureRiskPanel = ({futureRisk,adjustedScore,memoryData}) => {
  const trend      = futureRisk?.trend ?? 0;
  const predicted  = futureRisk?.predicted_risk ?? adjustedScore ?? 0;
  const stateTrend = futureRisk?.state_trend ?? 0;
  const riskInc    = futureRisk?.risk_increase ?? adjustedScore ?? 0;
  const confidence = futureRisk?.confidence ?? 1;

  const trendDir   = trend > 0.005 ? "↑ INCREASING" : trend < -0.005 ? "↓ DECREASING" : "→ STABLE";
  const trendColor = trend > 0.005 ? T.danger : trend < -0.005 ? T.success : T.amber;

  // Failure probability heuristic
  const failureProb = Math.min(1, predicted * (1 + Math.max(0, trend) * 8));
  const failLevel   = failureProb > 0.65 ? "HIGH" : failureProb > 0.35 ? "MEDIUM" : "LOW";
  const failColor   = failureProb > 0.65 ? T.danger : failureProb > 0.35 ? T.warning : T.success;

  // Time-to-risk estimate: assume linear trend continues
  const timeToRisk  = trend > 0.005 && predicted < 0.8
    ? Math.round((0.8 - predicted) / trend)
    : null;

  const horizons = [
    {label:"NEXT 5s",  risk:Math.min(1, adjustedScore + Math.max(0, trend) * 5 * 3),},
    {label:"NEXT 15s", risk:Math.min(1, adjustedScore + Math.max(0, trend) * 15 * 3),},
    {label:"NEXT 30s", risk:Math.min(1, adjustedScore + Math.max(0, trend) * 30 * 3),},
  ];

  return(
    <div>
      {/* Trend + level */}
      <div style={{display:"flex",gap:"8px",marginBottom:"10px"}}>
        <div style={{flex:1,padding:"10px 12px",borderRadius:"5px",background:`${trendColor}08`,border:`1px solid ${trendColor}30`}}>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"4px"}}>TREND</div>
          <div style={{fontSize:"16px",fontFamily:"'Orbitron',monospace",fontWeight:900,color:trendColor}}>{trendDir}</div>
          <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginTop:"3px"}}>slope {trend>0?"+":""}{(trend*1000).toFixed(2)}‰/frame</div>
        </div>
        <div style={{flex:1,padding:"10px 12px",borderRadius:"5px",background:`${failColor}08`,border:`1px solid ${failColor}30`}}>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"4px"}}>FAILURE PROB</div>
          <div style={{fontSize:"16px",fontFamily:"'Orbitron',monospace",fontWeight:900,color:failColor}}>{failLevel}</div>
          <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginTop:"3px"}}>{(failureProb*100).toFixed(0)}% probability</div>
        </div>
      </div>

      {/* Predicted risk bar */}
      <div style={{marginBottom:"10px"}}>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"4px"}}>
          <span style={{color:T.muted}}>PREDICTED RISK (next frame)</span>
          <span style={{color:predicted>0.5?T.danger:T.amber}}>{(predicted*100).toFixed(1)}%</span>
        </div>
        <div style={{height:"6px",borderRadius:"3px",background:"rgba(0,0,0,0.4)",overflow:"hidden"}}>
          <div style={{width:`${predicted*100}%`,height:"100%",background:predicted>0.65?T.danger:predicted>0.35?T.warning:T.success,transition:"width 0.8s ease"}}/>
        </div>
      </div>

      {/* Time-to-risk */}
      {timeToRisk!==null&&(
        <div style={{padding:"7px 11px",borderRadius:"4px",background:`${T.danger}08`,border:`1px solid ${T.danger}30`,marginBottom:"10px",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <span style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>TIME TO CRITICAL RISK</span>
          <span style={{fontSize:"14px",fontFamily:"'Orbitron',monospace",fontWeight:700,color:T.danger}}>~{timeToRisk}s</span>
        </div>
      )}

      {/* Horizon bars */}
      {horizons.map(({label,risk})=>{
        const c=risk>0.65?T.danger:risk>0.35?T.warning:T.success;
        return(
          <div key={label} style={{marginBottom:"7px"}}>
            <div style={{display:"flex",justifyContent:"space-between",fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
              <span style={{color:T.muted}}>{label}</span>
              <span style={{color:c}}>{(risk*100).toFixed(0)}%</span>
            </div>
            <div style={{height:"4px",borderRadius:"2px",background:"rgba(0,0,0,0.4)",overflow:"hidden"}}>
              <div style={{width:`${risk*100}%`,height:"100%",background:c,transition:"width 1s ease"}}/>
            </div>
          </div>
        );
      })}

      <div style={{marginTop:"8px",padding:"6px 10px",borderRadius:"3px",background:"rgba(0,0,0,0.3)",border:`1px solid ${T.border}`,fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",display:"flex",justifyContent:"space-between"}}>
        <span>model conf {(confidence*100).toFixed(0)}%</span>
        <span>state slope {stateTrend>0?"+":""}{(stateTrend*1000).toFixed(1)}‰</span>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   NEW: ENSEMBLE TRANSPARENCY PANEL
═══════════════════════════════════════════════════════════════ */
const EnsemblePanel = ({ensemble,anomaly}) => {
  const modelScores  = ensemble?.model_scores  ?? {};
  const modelWeights = ensemble?.model_weights ?? {};
  const disagreement = ensemble?.disagreement  ?? 0;
  const confidence   = ensemble?.confidence    ?? 1;
  const diversity    = ensemble?.diversity     ?? {};
  const rescued      = ensemble?.diversity_rescued ?? false;

  const models = [
    {key:"isolation_forest", label:"IF",   fullLabel:"Isolation Forest"},
    {key:"autoencoder",      label:"AE",   fullLabel:"Autoencoder"},
    {key:"lstm",             label:"LSTM", fullLabel:"LSTM"},
  ];

  const barData = models.map(m=>({
    name:m.label,
    score:Math.round((modelScores[m.key]??0)*100),
    weight:Math.round((modelWeights[m.key]??0.33)*100),
  }));

  return(
    <div>
      {/* Per-model score bars */}
      <div style={{marginBottom:"10px"}}>
        {models.map(m=>{
          const score=(modelScores[m.key]??0);
          const weight=(modelWeights[m.key]??0.33);
          const c=score>0.65?T.danger:score>0.35?T.warning:T.success;
          return(
            <div key={m.key} style={{marginBottom:"8px"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
                <span style={{color:T.cyan,minWidth:"40px"}}>{m.label}</span>
                <span style={{color:T.muted,flex:1,fontSize:"8px"}}>{m.fullLabel}</span>
                <span style={{color:c,marginLeft:"8px"}}>{(score*100).toFixed(0)}%</span>
                <span style={{color:T.muted,marginLeft:"8px",fontSize:"8px"}}>w:{(weight*100).toFixed(0)}%</span>
              </div>
              <div style={{height:"5px",borderRadius:"2px",background:"rgba(0,0,0,0.4)",overflow:"hidden",position:"relative"}}>
                <div style={{width:`${score*100}%`,height:"100%",background:c,transition:"width 0.6s ease"}}/>
                {/* Weight marker */}
                <div style={{position:"absolute",top:0,left:`${weight*100}%`,width:"1px",height:"100%",background:`${T.purple}80`}}/>
              </div>
            </div>
          );
        })}
      </div>

      {/* Agreement / disagreement */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"6px",marginBottom:"8px"}}>
        <div style={{padding:"8px 10px",borderRadius:"4px",background:`${disagreement>0.3?T.danger:T.success}08`,border:`1px solid ${disagreement>0.3?T.danger:T.success}30`}}>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>DISAGREEMENT</div>
          <div style={{fontSize:"16px",fontFamily:"'Orbitron',monospace",fontWeight:700,color:disagreement>0.3?T.danger:T.success}}>{(disagreement*100).toFixed(0)}%</div>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>{disagreement>0.3?"⚠ HIGH":"✓ LOW"}</div>
        </div>
        <div style={{padding:"8px 10px",borderRadius:"4px",background:`${T.cyan}08`,border:`1px solid ${T.cyan}25`}}>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>CONFIDENCE</div>
          <div style={{fontSize:"16px",fontFamily:"'Orbitron',monospace",fontWeight:700,color:T.cyan}}>{(confidence*100).toFixed(0)}%</div>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>ensemble</div>
        </div>
      </div>

      {/* Diversity */}
      <div style={{padding:"7px 10px",borderRadius:"4px",background:"rgba(0,0,0,0.3)",border:`1px solid ${T.border}`,fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",display:"flex",justifyContent:"space-between"}}>
        <span style={{color:T.muted}}>diversity σ={((diversity.std??0)*100).toFixed(1)}%  corr={diversity.avg_pairwise_corr??0}</span>
        {rescued&&<span style={{color:T.warning}}>⚠ RESCUED</span>}
      </div>

      {disagreement>0.3&&(
        <div style={{marginTop:"8px",padding:"7px 10px",borderRadius:"4px",background:`${T.warning}08`,border:`1px solid ${T.warning}35`,fontSize:"9px",color:T.warning,fontFamily:"'IBM Plex Mono',monospace"}}>
          ⚠ Models disagree — treat decision with lower trust
        </div>
      )}
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   NEW: UNCERTAINTY / TRUST PANEL
═══════════════════════════════════════════════════════════════ */
const TrustPanel = ({intelligence,ensemble,decision}) => {
  const conf       = intelligence?.confidence ?? decision?.confidence ?? 0;
  const disagree   = ensemble?.disagreement ?? intelligence?.disagreement ?? 0;
  const diversity  = ensemble?.diversity    ?? intelligence?.diversity  ?? {};
  const std        = diversity.std ?? 0;
  const uncertainty= 1 - conf;
  const trustScore = Math.max(0, conf - disagree * 0.5 - std * 0.3);
  const trustLevel = trustScore > 0.7 ? "HIGH" : trustScore > 0.4 ? "MEDIUM" : "LOW";
  const trustColor = trustScore > 0.7 ? T.success : trustScore > 0.4 ? T.warning : T.danger;

  const metrics = [
    {l:"SYSTEM CONFIDENCE", v:conf,       c:conf>0.75?T.success:T.warning,     d:`${(conf*100).toFixed(1)}%`},
    {l:"UNCERTAINTY INDEX",  v:uncertainty,c:uncertainty>0.35?T.danger:T.success,d:`${(uncertainty*100).toFixed(1)}%`},
    {l:"MODEL DISAGREEMENT", v:disagree,   c:disagree>0.3?T.danger:T.success,   d:`${(disagree*100).toFixed(0)}%`},
    {l:"SCORE DIVERSITY σ",  v:std,        c:std>0.25?T.warning:T.success,      d:`${(std*100).toFixed(1)}%`},
  ];

  return(
    <div>
      {/* Trust score hero */}
      <div style={{display:"flex",alignItems:"center",gap:"12px",marginBottom:"12px",padding:"10px 12px",borderRadius:"5px",background:`${trustColor}08`,border:`1px solid ${trustColor}35`}}>
        <div style={{textAlign:"center",minWidth:"55px"}}>
          <div style={{fontSize:"24px",fontWeight:900,color:trustColor,fontFamily:"'Orbitron',monospace"}}>{(trustScore*100).toFixed(0)}</div>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>TRUST</div>
        </div>
        <div style={{flex:1}}>
          <div style={{height:"6px",borderRadius:"3px",background:"rgba(0,0,0,0.4)",overflow:"hidden",marginBottom:"5px"}}>
            <div style={{width:`${trustScore*100}%`,height:"100%",background:trustColor,transition:"width 0.8s ease"}}/>
          </div>
          <div style={{fontSize:"10px",color:trustColor,fontFamily:"'Orbitron',monospace",fontWeight:700}}>{trustLevel} TRUST</div>
          <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginTop:"2px"}}>
            {trustLevel==="HIGH"?"Decisions reliable · proceed":"Cross-validate sensors"}
          </div>
        </div>
      </div>

      {metrics.map(({l,v,c,d})=>(
        <div key={l} style={{marginBottom:"8px"}}>
          <div style={{display:"flex",justifyContent:"space-between",fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
            <span style={{color:T.muted}}>{l}</span><span style={{color:c,fontWeight:500}}>{d}</span>
          </div>
          <div style={{height:"4px",borderRadius:"2px",background:"rgba(0,0,0,0.5)",overflow:"hidden"}}>
            <div style={{width:`${v*100}%`,height:"100%",background:`linear-gradient(90deg,${c}90,${c})`,transition:"width 0.8s ease"}}/>
          </div>
        </div>
      ))}
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   NEW: MEMORY / TREND PANEL
═══════════════════════════════════════════════════════════════ */
const MemoryTrendPanel = ({history}) => {
  const recent = history.slice(-30);
  const avg    = recent.length ? recent.reduce((s,h)=>s+(h.anomaly??0),0)/recent.length : 0;
  const trend  = recent.length>=2
    ? ((recent[recent.length-1].anomaly??0)-(recent[0].anomaly??0))/recent.length
    : 0;
  const trendColor = trend>0.3?T.danger:trend>0?T.warning:trend<0?T.success:T.muted;
  const trendLabel = trend>0.3?"ESCALATING":trend>0?"RISING":trend<0?"RECOVERING":"FLAT";

  return(
    <div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"8px"}}>
        <div>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>30-FRAME TREND</div>
          <div style={{fontSize:"14px",fontFamily:"'Orbitron',monospace",fontWeight:700,color:trendColor}}>{trendLabel}</div>
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>30f AVG ANOMALY</div>
          <div style={{fontSize:"14px",fontFamily:"'Orbitron',monospace",fontWeight:700,color:avg>0.5?T.danger:T.amber}}>{(avg).toFixed(2)}</div>
        </div>
      </div>

      <div style={{height:"80px",marginBottom:"6px"}}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={recent}>
            <defs>
              <linearGradient id="gM" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={T.purple} stopOpacity={0.4}/>
                <stop offset="100%" stopColor={T.purple} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <XAxis dataKey="t" hide/>
            <YAxis domain={[0,100]} hide/>
            <Area type="monotone" dataKey="anomaly" stroke={T.purple} fill="url(#gM)" strokeWidth={2} dot={false}/>
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",textAlign:"center"}}>
        anomaly score — last 30 frames
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════
   NEW: ACTION IMPACT PANEL
═══════════════════════════════════════════════════════════════ */
const ACTION_IMPACT = {
  AUTO_BRAKE:    {headline:"Emergency braking engaged",       impacts:["Reduces collision energy by ~70%","Stops vehicle in ~{dist}m at current speed","Activating hazard lights and brake assist"]},
  STEER_CORRECT: {headline:"Steering correction applied",     impacts:["Returns vehicle to lane centre","Prevents lane departure in ~{ttc}s","Lateral drift reduced by estimated 85%"]},
  REDUCE_SPEED:  {headline:"Speed reduction advised",         impacts:["Lowers kinetic energy, improves reaction margin","Following distance buffer increased","Brake wear reduced by ~30%"]},
  ALERT_DRIVER:  {headline:"Driver attention requested",      impacts:["Fatigue or distraction pattern detected","Maintains situational awareness","System confidence below full-auto threshold"]},
  INCREASE_DIST: {headline:"Following distance expansion",    impacts:["Current gap below safe 2s rule","Extends reaction time buffer","Reduces rear-end collision probability by ~50%"]},
  LANE_KEEP:     {headline:"Lane-keep assist active",         impacts:["Minor lateral drift detected","Gentle correction preventing departure","No driver action required yet"]},
  MAINTAIN:      {headline:"Nominal operation",               impacts:["All risk factors within acceptable range","Sensor fusion stable","Memory trend: flat or improving"]},
};

const ActionImpactPanel = ({decision,speed,ttc}) => {
  if(!decision) return <div style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>Awaiting decision...</div>;
  const {action,color,label} = decision;
  const cfg = ACTION_IMPACT[action] ?? ACTION_IMPACT.MAINTAIN;
  const stoppingDist = speed ? ((speed*0.44704)**2/(2*9.81*0.7)).toFixed(1) : "?";
  const ttcStr = ttc ? ttc.toFixed(1) : "?";

  const renderImpact = s => s.replace("{dist}",stoppingDist).replace("{ttc}",ttcStr);

  return(
    <div>
      <div style={{padding:"10px 13px",borderRadius:"5px",background:`${color}10`,border:`1px solid ${color}45`,marginBottom:"10px"}}>
        <div style={{fontSize:"9px",fontFamily:"'Orbitron',monospace",color,fontWeight:700,marginBottom:"4px"}}>{decision.icon} {label}</div>
        <div style={{fontSize:"11px",color:T.text,fontFamily:"'IBM Plex Mono',monospace",lineHeight:"1.5"}}>{cfg.headline}</div>
      </div>

      {cfg.impacts.map((impact,i)=>(
        <div key={i} style={{display:"flex",gap:"8px",alignItems:"flex-start",marginBottom:"7px",padding:"7px 10px",borderRadius:"4px",background:`${color}06`,borderLeft:`2px solid ${color}50`}}>
          <div style={{fontSize:"9px",color,minWidth:"12px",marginTop:"1px"}}>▸</div>
          <div style={{fontSize:"9px",color:T.text,fontFamily:"'IBM Plex Mono',monospace",lineHeight:"1.5"}}>{renderImpact(impact)}</div>
        </div>
      ))}

      {decision.urgency==="CRITICAL"&&(
        <div style={{marginTop:"8px",padding:"7px 10px",borderRadius:"4px",background:`${T.danger}10`,border:`1px solid ${T.danger}45`,fontSize:"9px",color:T.danger,fontFamily:"'IBM Plex Mono',monospace",animation:"blink 1s infinite"}}>
          ⚠ CRITICAL — bypasses hysteresis gate for immediate response
        </div>
      )}
    </div>
  );
};

/* ─── Decision Panel ─────────────────────────────────────────── */
const DecisionPanel = ({decision}) => {
  if(!decision)return<div style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>Awaiting...</div>;
  const {action,label,color,urgency,confidence,composite_score,ttc,reasoning_chain,hysteresis_held}=decision;
  const conf=confidence??0,comp=composite_score??0;
  return(<div>
    <div style={{padding:"14px 16px",borderRadius:"6px",background:`${color}12`,border:`2px solid ${color}50`,marginBottom:"11px",position:"relative",overflow:"hidden"}}>
      <div style={{position:"absolute",top:0,left:0,height:"3px",width:`${conf*100}%`,background:color,transition:"width 1.2s ease",boxShadow:`0 0 10px ${color}`}}/>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div>
          <div style={{fontSize:"20px",fontFamily:"'Orbitron',monospace",fontWeight:900,color,textShadow:`0 0 20px ${color}`,letterSpacing:"0.05em"}}>{decision.icon} {label}</div>
          <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginTop:"3px"}}>AUTONOMOUS ACTION {hysteresis_held?<span style={{color:T.amber}}> · HYSTERESIS HOLD</span>:null}</div>
        </div>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:"11px",fontFamily:"'Orbitron',monospace",fontWeight:700,color}}>{(conf*100).toFixed(0)}%</div>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>CONF</div>
          <div style={{marginTop:"4px",padding:"2px 6px",borderRadius:"3px",background:`${color}20`,border:`1px solid ${color}50`,fontSize:"8px",color,fontFamily:"'IBM Plex Mono',monospace"}}>{urgency}</div>
        </div>
      </div>
    </div>
    <div style={{marginBottom:"10px"}}>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
        <span style={{color:T.muted}}>COMPOSITE RISK SCORE</span><span style={{color}}>{(comp*100).toFixed(1)}%</span>
      </div>
      <div style={{height:"6px",borderRadius:"3px",background:"rgba(0,0,0,0.4)",overflow:"hidden",position:"relative"}}>
        <div style={{width:`${comp*100}%`,height:"100%",background:`linear-gradient(90deg,${comp>0.7?T.danger:comp>0.4?T.warning:T.success}80,${color})`,transition:"width 0.8s ease",boxShadow:`0 0 8px ${color}60`}}/>
        {[{t:0.82,l:"BRAKE"},{t:0.55,l:"STEER"},{t:0.3,l:"ALERT"}].map(({t:th,l})=>(
          <div key={l} style={{position:"absolute",top:0,left:`${th*100}%`,width:"1px",height:"100%",background:`${T.muted}60`}}/>
        ))}
      </div>
    </div>
    {ttc!=null&&(
      <div style={{display:"flex",alignItems:"center",gap:"10px",marginBottom:"10px",padding:"8px 12px",borderRadius:"4px",background:"rgba(0,0,0,0.4)",border:`1px solid ${ttc<3?T.danger:T.border}`}}>
        <div style={{flex:1}}>
          <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>TIME-TO-COLLISION</div>
          <div style={{height:"4px",borderRadius:"2px",background:"rgba(0,0,0,0.5)",overflow:"hidden"}}>
            <div style={{width:`${Math.min(100,((10-ttc)/10)*100)}%`,height:"100%",background:ttc<2.5?T.danger:ttc<5?T.warning:T.success,transition:"width 0.5s ease"}}/>
          </div>
        </div>
        <div style={{fontSize:"18px",fontFamily:"'Orbitron',monospace",fontWeight:900,color:ttc<2.5?T.danger:ttc<5?T.warning:T.success,animation:ttc<2.5?"ttcPulse 0.5s infinite":"none"}}>{ttc.toFixed(1)}s</div>
      </div>
    )}
    <div style={{marginBottom:"6px"}}>
      <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"5px",letterSpacing:"0.08em"}}>REASONING CHAIN</div>
      {(reasoning_chain||[]).map((r,i)=>(
        <div key={i} style={{padding:"5px 9px",borderRadius:"3px",background:`${color}08`,borderLeft:`2px solid ${color}`,marginBottom:"4px",fontSize:"9px",color:T.text,fontFamily:"'IBM Plex Mono',monospace"}}>{i+1}. {r}</div>
      ))}
    </div>
  </div>);
};

/* ─── Anomaly Panel ──────────────────────────────────────────── */
const AnomalyPanel = ({anomaly}) => {
  if(!anomaly)return<div style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>Collecting data...</div>;
  const score=anomaly.score??0,sc=score>0.65?T.danger:score>0.35?T.warning:T.success;
  const topSigs=anomaly.top_signals??[];
  return(<div>
    <div style={{display:"flex",alignItems:"center",gap:"12px",marginBottom:"11px",padding:"10px 12px",borderRadius:"5px",background:`${sc}08`,border:`1px solid ${sc}30`}}>
      <div style={{textAlign:"center",minWidth:"56px"}}>
        <div style={{fontSize:"24px",fontWeight:900,color:sc,fontFamily:"'Orbitron',monospace",textShadow:`0 0 10px ${sc}`}}>{(score*100).toFixed(0)}</div>
        <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>ANOMALY %</div>
      </div>
      <div style={{flex:1}}>
        <div style={{height:"6px",borderRadius:"3px",background:"rgba(0,0,0,0.4)",overflow:"hidden",marginBottom:"5px"}}>
          <div style={{width:`${score*100}%`,height:"100%",background:sc,boxShadow:`0 0 8px ${sc}60`,transition:"width 0.6s ease"}}/>
        </div>
        <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>{anomaly.severity} · {anomaly.model_type}</div>
        <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>{anomaly.trained_samples??0} samples trained</div>
      </div>
    </div>
    <div style={{marginBottom:"8px"}}>
      <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"5px"}}>TOP ANOMALOUS SIGNALS</div>
      {topSigs.slice(0,5).map(({signal,contribution,value})=>{
        const c=contribution>0.65?T.danger:contribution>0.35?T.warning:T.success;
        return(<div key={signal} style={{display:"flex",alignItems:"center",gap:"8px",marginBottom:"5px"}}>
          <div style={{width:"75px",fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",flexShrink:0}}>{signal}</div>
          <div style={{flex:1,height:"4px",borderRadius:"2px",background:"rgba(0,0,0,0.4)",overflow:"hidden"}}>
            <div style={{width:`${contribution*100}%`,height:"100%",background:c,transition:"width 0.5s ease"}}/>
          </div>
          <div style={{width:"40px",textAlign:"right",fontSize:"8px",color:c,fontFamily:"'IBM Plex Mono',monospace"}}>{value?.toFixed(2)}</div>
        </div>);
      })}
    </div>
    {anomaly.temporal_break&&<div style={{padding:"7px 10px",borderRadius:"4px",background:`${T.danger}08`,border:`1px solid ${T.danger}30`,fontSize:"9px",color:T.danger,fontFamily:"'IBM Plex Mono',monospace"}}>⚠ TEMPORAL PATTERN BREAK — sequence disrupted</div>}
  </div>);
};

/* ─── Sensor Staleness ───────────────────────────────────────── */
const SensorStalenessPanel = ({staleness,obdConnected,imuConnected,gpsConnected}) => {
  const sources=[{key:"imu",label:"IMU  (MPU-6050)",icon:"◎",connected:imuConnected},{key:"obd",label:"OBD-II (ELM327)",icon:"⚙",connected:obdConnected},{key:"gps",label:"GPS   (gpsd)",icon:"◈",connected:gpsConnected},{key:"synthetic",label:"SYNTHETIC",icon:"⟳",connected:true}];
  return(<div>
    {sources.map(({key,label,icon,connected})=>{
      const status=staleness?.[key]??"UNKNOWN",isOk=status.startsWith("OK"),isStale=status.startsWith("STALE");
      const c=!connected?"#666":isOk?T.success:isStale?T.danger:T.warning;
      const badge=!connected?"OFFLINE":isOk?"LIVE":isStale?"STALE":"UNKNOWN";
      return(<div key={key} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"8px 11px",borderRadius:"4px",background:`${c}06`,border:`1px solid ${c}25`,marginBottom:"6px"}}>
        <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
          <div style={{width:"7px",height:"7px",borderRadius:"50%",background:c,boxShadow:`0 0 6px ${c}`,animation:isOk?"pulse 2s infinite":"none"}}/>
          <div>
            <div style={{fontSize:"9px",color:T.text,fontFamily:"'IBM Plex Mono',monospace"}}>{icon} {label}</div>
            <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginTop:"1px"}}>{status}</div>
          </div>
        </div>
        <div style={{padding:"2px 7px",borderRadius:"3px",background:`${c}15`,border:`1px solid ${c}40`,fontSize:"8px",color:c,fontFamily:"'IBM Plex Mono',monospace"}}>{badge}</div>
      </div>);
    })}
  </div>);
};

/* ─── Latency Panel ──────────────────────────────────────────── */
const LatencyPanel = ({latency,pipelineMs,watchdogState}) => {
  const stages=[{key:"vision",label:"Vision (YOLO+MiDaS)",target:30},{key:"fusion",label:"Kalman Fusion",target:10},{key:"anomaly",label:"Anomaly Ensemble",target:15},{key:"decision",label:"Decision Engine",target:5}];
  const wColor=watchdogState==="STALE"?T.danger:watchdogState==="SLOW"?T.warning:T.success;
  return(<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"8px 11px",borderRadius:"4px",background:`${wColor}08`,border:`1px solid ${wColor}30`,marginBottom:"10px"}}>
      <div>
        <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"2px"}}>TOTAL PIPELINE</div>
        <div style={{fontSize:"16px",fontFamily:"'Orbitron',monospace",fontWeight:700,color:wColor}}>{(pipelineMs??0).toFixed(1)}<span style={{fontSize:"9px",color:T.muted}}>ms</span></div>
      </div>
      <div style={{textAlign:"right"}}>
        <div style={{padding:"3px 8px",borderRadius:"3px",background:`${wColor}20`,fontSize:"9px",color:wColor,fontFamily:"'IBM Plex Mono',monospace"}}>{watchdogState}</div>
        <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginTop:"3px"}}>{pipelineMs>200?"OVER BUDGET":"WITHIN BUDGET"}</div>
      </div>
    </div>
    {stages.map(({key,label,target})=>{
      const ms=latency?.[key]??0,c=ms>target?T.danger:ms>target*0.8?T.warning:T.success,pct=Math.min(100,(ms/target)*100);
      return(<div key={key} style={{marginBottom:"9px"}}>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
          <span style={{color:T.muted}}>{label}</span>
          <span style={{display:"flex",gap:"8px"}}><span style={{color:c}}>{ms.toFixed(1)}ms</span><span style={{color:T.muted}}>/{target}ms</span></span>
        </div>
        <div style={{height:"4px",borderRadius:"2px",background:"rgba(0,0,0,0.4)",overflow:"hidden"}}>
          <div style={{width:`${pct}%`,height:"100%",background:c,transition:"width 0.5s ease"}}/>
        </div>
      </div>);
    })}
  </div>);
};

/* ─── Depth Calibration ──────────────────────────────────────── */
const DepthCalibIndicator = ({depthCalib}) => {
  const calibrated=depthCalib?.calibrated??false,kScale=depthCalib?.k_scale??5.5;
  const c=calibrated?T.success:T.amber;
  return(<div style={{padding:"7px 10px",borderRadius:"4px",background:`${c}08`,border:`1px solid ${c}25`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
    <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
      <div style={{width:"6px",height:"6px",borderRadius:"50%",background:c,animation:calibrated?"pulse 3s infinite":"pulse 0.8s infinite"}}/>
      <div>
        <div style={{fontSize:"9px",color:c,fontFamily:"'Orbitron',monospace",fontWeight:700}}>{calibrated?"DEPTH CALIBRATED":"DEPTH LEARNING"}</div>
        <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>K-scale: {kScale.toFixed(3)} m</div>
      </div>
    </div>
    <div style={{fontSize:"8px",color:c,fontFamily:"'IBM Plex Mono',monospace"}}>{calibrated?"✓ METRIC":"⟳ COLLECTING"}</div>
  </div>);
};

/* ─── Validation Panel ───────────────────────────────────────── */
const ValidationPanel = ({metrics}) => {
  if(!metrics)return null;
  const {tp,fp,tn,fn,precision,recall,f1,fpRate,stability,total}=metrics;
  const items=[{l:"PRECISION",v:precision,c:precision>80?T.success:precision>60?T.warning:T.danger},{l:"RECALL",v:recall,c:recall>80?T.success:recall>60?T.warning:T.danger},{l:"F1 SCORE",v:f1,c:f1>80?T.success:f1>60?T.warning:T.danger},{l:"FP RATE",v:fpRate,c:fpRate<5?T.success:fpRate<15?T.warning:T.danger},{l:"HYSTERESIS STABILITY",v:stability,c:stability>80?T.success:T.warning}];
  return(<div>
    <div style={{display:"flex",gap:"6px",marginBottom:"10px"}}>
      {[{l:"TP",v:tp,c:T.success},{l:"FP",v:fp,c:T.danger},{l:"TN",v:tn,c:T.cyan},{l:"FN",v:fn,c:T.warning}].map(({l,v,c})=>(
        <div key={l} style={{flex:1,padding:"6px",textAlign:"center",background:`${c}08`,borderRadius:"4px",border:`1px solid ${c}25`}}>
          <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>{l}</div>
          <div style={{fontSize:"13px",fontWeight:700,color:c,fontFamily:"'Orbitron',monospace"}}>{v}</div>
        </div>
      ))}
    </div>
    {items.map(({l,v,c})=>(
      <div key={l} style={{marginBottom:"7px"}}>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
          <span style={{color:T.muted}}>{l}</span><span style={{color:c}}>{v.toFixed(1)}%</span>
        </div>
        <div style={{height:"4px",borderRadius:"2px",background:"rgba(0,0,0,0.5)",overflow:"hidden"}}>
          <div style={{width:`${v}%`,height:"100%",background:c,transition:"width 0.6s ease"}}/>
        </div>
      </div>
    ))}
    <div style={{padding:"6px 10px",borderRadius:"3px",background:"rgba(0,0,0,0.3)",border:`1px solid ${T.border}`,display:"flex",justifyContent:"space-between",fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",marginTop:"4px"}}>
      <span style={{color:T.muted}}>TOTAL DECISIONS</span><span style={{color:T.cyan}}>{total}</span>
    </div>
  </div>);
};

/* ─── AI Thinking Flow ───────────────────────────────────────── */
const AIThinkingFlow = ({chain=[]}) => {
  const [visible,setVisible]=useState([]);
  const key=chain.join("|");
  useEffect(()=>{
    setVisible([]);if(!chain.length)return;
    const ts=chain.map((_,i)=>setTimeout(()=>setVisible(v=>[...v,i]),i*280));
    return()=>ts.forEach(clearTimeout);
  },[key]);
  return(<div style={{position:"relative",padding:"2px 0"}}>
    {chain.length===0
      ?<div style={{fontSize:"10px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",animation:"pulse 2s infinite"}}>◉ AWAITING INPUT...</div>
      :chain.map((step,i)=>(
        <div key={i} style={{display:"flex",alignItems:"flex-start",gap:"10px",marginBottom:"8px",opacity:visible.includes(i)?1:0,transform:visible.includes(i)?"translateX(0)":"translateX(-12px)",transition:"all 0.35s cubic-bezier(0.4,0,0.2,1)"}}>
          <div style={{display:"flex",flexDirection:"column",alignItems:"center",minWidth:"22px"}}>
            <div style={{width:"20px",height:"20px",borderRadius:"50%",flexShrink:0,border:`1.5px solid ${T.purple}`,background:`${T.purple}15`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:"8px",fontWeight:700,color:T.purple,fontFamily:"'Orbitron',monospace"}}>{i+1}</div>
            {i<chain.length-1&&<div style={{width:"1px",flex:1,minHeight:"8px",background:`linear-gradient(${T.purple}60,${T.purple}15)`,marginTop:"3px"}}/>}
          </div>
          <div style={{flex:1,paddingTop:"2px",fontSize:"10px",color:T.text,fontFamily:"'IBM Plex Mono',monospace",lineHeight:"1.5"}}>
            {step.includes("→")?step.split("→").map((p,pi)=>(<span key={pi}>{pi>0&&<span style={{color:T.purple,margin:"0 4px"}}>→</span>}<span style={{color:pi===step.split("→").length-1?T.amber:T.text}}>{p.trim()}</span></span>)):step}
          </div>
        </div>
      ))}
  </div>);
};

/* ─── Component health ───────────────────────────────────────── */
const CompItem = ({label,health,icon,issue}) => {
  const c=health>75?T.success:health>45?T.warning:T.danger;
  return(<div style={{padding:"9px 11px",borderRadius:"5px",background:issue?"rgba(255,30,64,0.06)":"rgba(0,200,255,0.03)",border:`1px solid ${issue?`${T.danger}40`:T.border}`,transition:"all 0.2s"}}
    onMouseEnter={e=>{e.currentTarget.style.transform="translateY(-2px)";e.currentTarget.style.borderColor=`${c}55`;}}
    onMouseLeave={e=>{e.currentTarget.style.transform="";e.currentTarget.style.borderColor=issue?`${T.danger}40`:T.border;}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"5px"}}>
      <div style={{fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",color:T.text}}>{icon} {label}</div>
      <div style={{fontSize:"10px",fontWeight:700,fontFamily:"'Orbitron',monospace",color:c}}>{(health??0).toFixed(0)}%</div>
    </div>
    <div style={{height:"3px",borderRadius:"2px",background:"rgba(0,0,0,0.5)",overflow:"hidden"}}>
      <div style={{width:`${health??0}%`,height:"100%",background:`linear-gradient(90deg,${c}80,${c})`,boxShadow:`0 0 5px ${c}60`,transition:"width 1s ease"}}/>
    </div>
    {issue&&<div style={{fontSize:"8px",color:T.danger,marginTop:"3px",fontFamily:"'IBM Plex Mono',monospace"}}>⚠ {issue}</div>}
  </div>);
};

/* ─── Driver Behavior ─────────────────────────────────────────── */
const DriverBehaviorPanel = ({driver={}}) => {
  const attention=driver.attention_score??0.88,fatigue=driver.fatigue_level??0.15;
  const aggression=driver.aggression??0.22,reaction=driver.reaction_time??0.28;
  const radarData=[{subject:"ATTN",A:attention*100},{subject:"CALM",A:(1-aggression)*100},{subject:"ALERT",A:(1-fatigue)*100},{subject:"REACT",A:Math.max(0,(0.5-reaction)/0.5)*100},{subject:"FOCUS",A:(attention*0.7+(1-fatigue)*0.3)*100}];
  const overall=(attention*0.35+(1-fatigue)*0.3+(1-aggression)*0.2+Math.max(0,(0.5-reaction)/0.5)*0.15)*100;
  const oc=overall>75?T.success:overall>50?T.warning:T.danger;
  return(<div>
    <div style={{display:"flex",gap:"10px",marginBottom:"10px",alignItems:"center"}}>
      <div style={{flex:"0 0 auto"}}>
        <ResponsiveContainer width={110} height={110}>
          <RadarChart data={radarData} outerRadius={36}>
            <PolarGrid stroke={`${T.cyan}15`}/>
            <PolarAngleAxis dataKey="subject" tick={{fill:T.muted,fontSize:6,fontFamily:"'IBM Plex Mono',monospace"}}/>
            <Radar name="Driver" dataKey="A" stroke={T.purple} fill={T.purple} fillOpacity={0.18} strokeWidth={1.5}/>
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div style={{flex:1}}>
        <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"2px"}}>DRIVER SCORE</div>
        <div style={{fontSize:"20px",fontFamily:"'Orbitron',monospace",fontWeight:900,color:oc}}>{overall.toFixed(0)}<span style={{fontSize:"10px",color:T.muted}}>/100</span></div>
        <div style={{padding:"3px 7px",borderRadius:"3px",background:`${oc}10`,border:`1px solid ${oc}30`,fontSize:"8px",color:oc,fontFamily:"'IBM Plex Mono',monospace",marginTop:"4px"}}>{driver.style||"MODERATE"}</div>
      </div>
    </div>
    {[{label:"ATTENTION",value:attention,max:1,color:attention<0.6?T.danger:T.success,display:`${(attention*100).toFixed(0)}%`},{label:"FATIGUE",value:fatigue,max:1,color:fatigue>0.5?T.danger:T.amber,display:`${(fatigue*100).toFixed(0)}%`},{label:"AGGRESSION",value:aggression,max:1,color:aggression>0.5?T.danger:T.warning,display:`${(aggression*100).toFixed(0)}%`},{label:"REACTION",value:reaction,max:0.5,color:reaction>0.35?T.danger:T.success,display:`${(reaction*1000).toFixed(0)}ms`}].map(({label,value,max,color,display})=>(
      <div key={label} style={{marginBottom:"7px"}}>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
          <span style={{color:T.muted}}>{label}</span><span style={{color,fontWeight:500}}>{display}</span>
        </div>
        <div style={{height:"4px",borderRadius:"2px",background:"rgba(0,0,0,0.5)",overflow:"hidden"}}>
          <div style={{width:`${Math.min(value,max)/max*100}%`,height:"100%",background:`linear-gradient(90deg,${color}80,${color})`,transition:"width 0.6s ease"}}/>
        </div>
      </div>
    ))}
    {fatigue>0.5&&<div style={{padding:"7px 10px",borderRadius:"4px",background:`${T.danger}08`,border:`1px solid ${T.danger}35`,fontSize:"9px",color:T.danger,fontFamily:"'IBM Plex Mono',monospace",animation:"blink 1.5s infinite",marginTop:"6px"}}>⚠ FATIGUE ALERT — Consider rest stop</div>}
  </div>);
};

/* ─── Simulation Control ─────────────────────────────────────── */
const SimulationControl = ({onSimulate,activeScenario}) => {
  const scenarios=[
    {id:"pothole",label:"POTHOLE",icon:"⬛",color:T.amber,endpoint:"/simulate/pothole",desc:"Road impact"},
    {id:"brake_failure",label:"BRAKE FAIL",icon:"⊘",color:T.danger,endpoint:"/simulate/brake-failure",desc:"Hydraulic drop"},
    {id:"collision",label:"COLLISION",icon:"⚡",color:T.danger,endpoint:"/simulate/collision",desc:"Front impact"},
    {id:"engine_overheat",label:"OVERHEAT",icon:"🌡",color:T.warning,endpoint:"/simulate/overheat",desc:"Temp spike"},
    {id:"lane_depart",label:"LANE DRIFT",icon:"↔",color:T.cyan,endpoint:"/simulate/lane-depart",desc:"Boundary breach"},
    {id:"tire_blowout",label:"BLOWOUT",icon:"○",color:T.warning,endpoint:"/simulate/tire-blowout",desc:"Pressure loss"},
    {id:"fatigue",label:"FATIGUE",icon:"👁",color:T.purple,endpoint:"/simulate/fatigue",desc:"Drowsiness"},
    {id:"clear",label:"CLEAR ALL",icon:"✓",color:T.success,endpoint:"/simulate/clear",desc:"Reset nominal"},
  ];
  return(<div>
    <div style={{marginBottom:"9px",padding:"7px 10px",borderRadius:"4px",background:`${T.amber}08`,border:`1px solid ${T.amber}25`,fontSize:"9px",color:T.amber,fontFamily:"'IBM Plex Mono',monospace"}}>⚠ INJECT SCENARIO — tests decision response</div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"6px"}}>
      {scenarios.map(sc=>{
        const isActive=activeScenario===sc.id;
        return(<button key={sc.id} className="sim-btn" onClick={()=>onSimulate(sc)}
          style={{background:isActive?`${sc.color}20`:"rgba(0,0,0,0.35)",borderColor:isActive?sc.color:`${sc.color}40`,color:isActive?sc.color:`${sc.color}cc`,boxShadow:isActive?`0 0 14px ${sc.color}30`:"none"}}>
          <div style={{fontSize:"14px",marginBottom:"2px"}}>{sc.icon}</div>
          <div style={{fontSize:"8px",fontWeight:700}}>{sc.label}</div>
          <div style={{fontSize:"7px",opacity:0.6,fontFamily:"'IBM Plex Mono',monospace"}}>{sc.desc}</div>
        </button>);
      })}
    </div>
    {activeScenario&&activeScenario!=="clear"&&<div style={{marginTop:"8px",padding:"7px 10px",borderRadius:"4px",background:`${T.danger}08`,border:`1px solid ${T.danger}35`,fontSize:"9px",color:T.danger,fontFamily:"'IBM Plex Mono',monospace",animation:"blink 1.5s infinite"}}>◉ SCENARIO ACTIVE: {scenarios.find(s=>s.id===activeScenario)?.label}</div>}
  </div>);
};

/* ─── Event log ──────────────────────────────────────────────── */
const SEV_C={CRITICAL:T.danger,WARNING:T.warning,CAUTION:T.amber,INFO:T.cyan,SUCCESS:T.success};
const SEV_I={CRITICAL:"⬛",WARNING:"▲",CAUTION:"◆",INFO:"◈",SUCCESS:"✓"};
let _evId=0;
const makeEvent=(type,message,severity="INFO")=>({id:++_evId,time:new Date().toLocaleTimeString("en-US",{hour12:false,hour:"2-digit",minute:"2-digit",second:"2-digit"}),type,message,severity});

const EventLogPanel = ({events}) => {
  const logRef=useRef(null);
  useEffect(()=>{if(logRef.current)logRef.current.scrollTop=0;},[events.length]);
  return(<div>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"8px"}}>
      <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>{events.length} EVENTS</div>
      <div style={{display:"flex",gap:"6px"}}>
        {["CRITICAL","WARNING","SUCCESS"].map(s=>(
          <div key={s} style={{display:"flex",alignItems:"center",gap:"3px",fontSize:"7px",color:SEV_C[s],fontFamily:"'IBM Plex Mono',monospace"}}>
            <span style={{width:"5px",height:"5px",borderRadius:"50%",background:SEV_C[s],display:"inline-block"}}/>
            {events.filter(e=>e.severity===s).length}
          </div>
        ))}
      </div>
    </div>
    <div ref={logRef} style={{maxHeight:"220px",overflowY:"auto",display:"flex",flexDirection:"column",gap:"4px"}}>
      {events.length===0
        ?<div style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",padding:"8px"}}>Awaiting events...</div>
        :events.map((ev,idx)=>{
          const c=SEV_C[ev.severity]||T.cyan;
          return(<div key={ev.id} style={{padding:"7px 10px",borderRadius:"4px",background:`${c}06`,borderLeft:`2px solid ${c}`,animation:idx===0?"logSlide 0.3s ease-out":"none",flexShrink:0}}>
            <div style={{display:"flex",justifyContent:"space-between",marginBottom:"2px"}}>
              <span style={{fontSize:"8px",color:c,fontFamily:"'IBM Plex Mono',monospace",fontWeight:600}}>{SEV_I[ev.severity]} {ev.type}</span>
              <span style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>{ev.time}</span>
            </div>
            <div style={{fontSize:"9px",color:T.text,fontFamily:"'IBM Plex Mono',monospace",lineHeight:"1.45"}}>{ev.message}</div>
          </div>);
        })}
    </div>
  </div>);
};

/* ═══════════════════════════════════════════════════════════════
   MAIN DASHBOARD
═══════════════════════════════════════════════════════════════ */
const WS_URL="ws://localhost:8000/ws/stream";
const REST_URL="http://localhost:8000/vehicle/analyze-camera";
const SIM_URL="http://localhost:8000";

export default function Dashboard() {
  const videoRef=useRef(null),overlayRef=useRef(null),canvasRef=useRef(null);
  const wsRef=useRef(null),frameBuffer=useRef([]),validRef=useRef(new ValidationTracker());
  const prevDanger=useRef("SAFE");

  const [data,         setData]          = useState({});
  const [events,       setEvents]        = useState([]);
  const [camError,     setCamError]      = useState(false);
  const [wsConnected,  setWsConnected]   = useState(false);
  const [activeScenario,setActiveScenario]=useState(null);
  const [history,      setHistory]       = useState([]);
  const [lastFrameTs,  setLastFrameTs]   = useState(Date.now());
  const [validMetrics, setValidMetrics]  = useState(null);
  const [obdConnected, setObdConnected]  = useState(false);
  const [imuConnected, setImuConnected]  = useState(false);
  const [gpsConnected, setGpsConnected]  = useState(false);

  /* ── Derived ────────────────────────────────────────────── */
  const hazard      = data.risk?.hazard         ?? 0;
  const anomScore   = data.anomaly?.score        ?? 0;
  const adjustedScore = data.risk?.anomaly_score ?? anomScore;
  const color       = hazard>0.75?"#ff1e40":hazard>0.45?"#ff9500":"#00e87a";
  const dangerLevel = hazard>0.75?"CRITICAL":hazard>0.45?"WARNING":"SAFE";
  const features    = data.perception?.features  ?? {};
  const signals     = data.perception?.signals   ?? {};
  const objects     = data.perception?.objects   ?? [];
  const advisories  = data.decision_support?.advisories ?? data.decision?.advisories ?? [];
  const issues      = data.decision_support?.component_issues ?? [];
  const confidence  = data.intelligence?.confidence ?? data.decision?.confidence ?? 0;
  const chain       = data.explainability?.chain    ?? data.decision?.reasoning_chain ?? [];
  const predictions = data.prediction?.predictions  ?? [];
  const compHealth  = data.component_health         ?? {};
  const driver      = data.driver_profile           ?? {};
  const roadCond    = data.road_conditions          ?? {};
  const speed       = features.speed_estimate       ?? 0;
  const thermal     = features.thermal              ?? 0;
  const vibration   = features.vibration_intensity  ?? 0;
  const pipelineMs  = data.intelligence?.meta?.pipeline_ms ?? 0;
  const staleness   = data.sensor_staleness         ?? {};
  const depthCalib  = data.depth_calibration        ?? {};
  const ensemble    = data.ensemble                 ?? {};
  const futureRisk  = data.future_risk              ?? {};
  const memoryData  = data.memory_context?.memory   ?? {};
  const temporal    = data.temporal                 ?? {};
  const failsafe    = data.failsafe_mode            ?? "NORMAL";
  const ttc         = data.decision?.ttc;

  const watchdogState = useWatchdog(lastFrameTs, pipelineMs);

  // System health: composite of confidence + latency + sensor connectivity
  const systemHealth = useMemo(()=>{
    const confScore    = confidence * 35;
    const latScore     = pipelineMs < 100 ? 35 : pipelineMs < 200 ? 20 : 5;
    const sensorScore  = ((obdConnected?10:0)+(imuConnected?10:0)+(gpsConnected?10:0));
    const watchScore   = watchdogState==="OK"?20:watchdogState==="SLOW"?10:0;
    return Math.min(100, confScore + latScore + sensorScore + watchScore);
  },[confidence, pipelineMs, obdConnected, imuConnected, gpsConnected, watchdogState]);

  const pushEvent=useCallback((type,message,severity="INFO")=>{
    setEvents(prev=>[makeEvent(type,message,severity),...prev].slice(0,80));
  },[]);

  /* ── WebSocket ──────────────────────────────────────────── */
  useEffect(()=>{
    let reconnectTimer;
    function connect(){
      if(wsRef.current?.readyState===WebSocket.OPEN)return;
      pushEvent("SYSTEM","WebSocket connecting...","INFO");
      const ws=new WebSocket(WS_URL);wsRef.current=ws;
      ws.onopen=()=>{setWsConnected(true);pushEvent("SYSTEM","WebSocket CONNECTED — real-time stream active","SUCCESS");};
      ws.onmessage=(event)=>{
        try{
          const d=JSON.parse(event.data);
          setData(d);setLastFrameTs(Date.now());
          frameBuffer.current.push(d);if(frameBuffer.current.length>500)frameBuffer.current.shift();
          validRef.current.record(d.decision,d.risk?.hazard,d.hysteresis?.held);
          setValidMetrics({...validRef.current.metrics()});
        }catch(e){console.error("WS parse error:",e);}
      };
      ws.onerror=()=>{pushEvent("SYSTEM","WebSocket error — will reconnect","WARNING");};
      ws.onclose=()=>{setWsConnected(false);pushEvent("SYSTEM","WebSocket closed — reconnecting...","CAUTION");reconnectTimer=setTimeout(connect,3000);};
    }
    connect();
    const healthId=setInterval(async()=>{
      try{const r=await fetch(`${SIM_URL}/health`);const h=await r.json();setObdConnected(h.obd_connected??false);setImuConnected(h.imu_connected??false);setGpsConnected(h.gps_connected??false);}catch{}
    },5000);
    return()=>{clearTimeout(reconnectTimer);clearInterval(healthId);wsRef.current?.close();};
  },[]);

  /* ── Fallback REST polling ─────────────────────────────── */
  useEffect(()=>{
    if(wsConnected)return;
    let active=true;
    const poll=async()=>{
      if(!active||wsConnected)return;
      const canvas=canvasRef.current,video=videoRef.current;
      if(!canvas||!video||video.readyState<2)return;
      canvas.width=640;canvas.height=480;canvas.getContext("2d")?.drawImage(video,0,0);
      canvas.toBlob(async blob=>{
        if(!blob)return;
        const form=new FormData();form.append("file",blob);
        try{const r=await fetch(REST_URL,{method:"POST",body:form});const d=await r.json();setData(d);setLastFrameTs(Date.now());}catch{}
      });
    };
    const id=setInterval(poll,1000);
    return()=>{active=false;clearInterval(id);};
  },[wsConnected]);

  /* ── Camera ─────────────────────────────────────────────── */
  useEffect(()=>{
    navigator.mediaDevices?.getUserMedia({video:{width:640,height:480}})
      .then(stream=>{if(videoRef.current)videoRef.current.srcObject=stream;pushEvent("SYSTEM","Camera ONLINE","SUCCESS");})
      .catch(()=>{setCamError(true);pushEvent("SYSTEM","Camera OFFLINE — signals-only mode","WARNING");});
    return()=>{if(videoRef.current?.srcObject)videoRef.current.srcObject.getTracks().forEach(t=>t.stop());};
  },[]);

  /* ── Canvas overlay ─────────────────────────────────────── */
  useEffect(()=>{
    const overlay=overlayRef.current,video=videoRef.current;if(!overlay||!video)return;
    const ctx=overlay.getContext("2d");let rafId;
    const draw=()=>{
      const W=video.videoWidth||640,H=video.videoHeight||480;overlay.width=W;overlay.height=H;ctx.clearRect(0,0,W,H);
      const sy=(Date.now()*0.05)%H;ctx.fillStyle="rgba(0,200,255,0.025)";ctx.fillRect(0,sy,W,2);
      const h=hazard;
      if(h>0.5){ctx.strokeStyle=`rgba(255,30,64,${0.08+h*0.1})`;ctx.lineWidth=0.4;ctx.setLineDash([4,8]);for(let gx=0;gx<W;gx+=40){ctx.beginPath();ctx.moveTo(gx,0);ctx.lineTo(gx,H);ctx.stroke();}for(let gy=0;gy<H;gy+=40){ctx.beginPath();ctx.moveTo(0,gy);ctx.lineTo(W,gy);ctx.stroke();}ctx.setLineDash([]);}
      const vpX=W/2,vpY=H*0.45,lOff=(roadCond.lane_offset??0),lW=W*0.28;
      [[vpX-lW-lOff*60,T.success],[vpX+lW-lOff*60,T.success]].forEach(([lx,lc],li)=>{
        const lColor=Math.abs(lOff)>0.4?T.danger:lc;
        ctx.beginPath();ctx.moveTo(lx+(li===0?-20:20),vpY);ctx.lineTo(lx+(li===0?-W*0.18:W*0.18),H);
        ctx.strokeStyle=`${lColor}60`;ctx.lineWidth=3;ctx.setLineDash([15,12]);ctx.shadowColor=lColor;ctx.shadowBlur=6;ctx.stroke();ctx.setLineDash([]);ctx.shadowBlur=0;
      });
      // Risk-coloured bounding boxes
      objects.forEach((obj,i)=>{
        const [bx,by,bw,bh]=obj.box??[W*0.35+i*20,H*0.25,W*0.28,H*0.38];
        // Risk-colour: red for pedestrians/critical, yellow for warning, cyan otherwise
        const riskScore=obj.label==="PERSON"?1.2:obj.type==="vehicle"?1.0:0.8;
        const oc=obj.label==="PERSON"?T.warning:(obj.distance??15)<6?T.danger:T.cyan;
        ctx.strokeStyle=oc;ctx.lineWidth=2;ctx.shadowColor=oc;ctx.shadowBlur=8;
        const cs=16;
        [[bx,by],[bx+bw,by],[bx,by+bh],[bx+bw,by+bh]].forEach(([px,py],qi)=>{
          ctx.beginPath();
          if(qi===0){ctx.moveTo(px+cs,py);ctx.lineTo(px,py);ctx.lineTo(px,py+cs);}
          else if(qi===1){ctx.moveTo(px-cs,py);ctx.lineTo(px,py);ctx.lineTo(px,py+cs);}
          else if(qi===2){ctx.moveTo(px,py-cs);ctx.lineTo(px,py);ctx.lineTo(px+cs,py);}
          else{ctx.moveTo(px-cs,py);ctx.lineTo(px,py);ctx.lineTo(px,py-cs);}
          ctx.stroke();
        });
        ctx.shadowBlur=0;
        const lt=`${(obj.label||"OBJ").toUpperCase()}  ${((obj.conf??0)*100).toFixed(0)}%${obj.distance?`  ${obj.distance.toFixed(1)}m`:""}`;
        ctx.font="bold 10px 'IBM Plex Mono',monospace";const tw=ctx.measureText(lt).width+12;
        ctx.fillStyle=`${oc}dd`;roundRect(ctx,bx,by-18,tw,17,3);
        ctx.fillStyle="#000a14";ctx.fillText(lt,bx+6,by-6);
        // TTC label on box
        if(obj.ttc!=null){
          const tc=obj.ttc<2.5?T.danger:obj.ttc<5?T.warning:T.amber;
          ctx.font="bold 11px 'Orbitron',monospace";const tw2=ctx.measureText(`TTC ${obj.ttc.toFixed(1)}s`).width+10;
          ctx.fillStyle=`${tc}cc`;roundRect(ctx,bx+bw-tw2-4,by+4,tw2,16,3);
          ctx.fillStyle="#fff";ctx.fillText(`TTC ${obj.ttc.toFixed(1)}s`,bx+bw-tw2,by+15);
        }
      });
      ctx.fillStyle="rgba(0,0,0,0.55)";roundRect(ctx,4,4,200,20,3);
      ctx.fillStyle=T.cyan;ctx.font="9px 'Orbitron',monospace";
      ctx.fillText(`OBJ:${objects.length}  HAZARD:${(h*100).toFixed(0)}%  ${dangerLevel}`,8,18);
      rafId=requestAnimationFrame(draw);
    };
    draw();return()=>cancelAnimationFrame(rafId);
  },[hazard,objects,roadCond.lane_offset,dangerLevel]);

  /* ── Event triggers ─────────────────────────────────────── */
  useEffect(()=>{
    if(!data.risk)return;
    if(dangerLevel==="CRITICAL"&&prevDanger.current!=="CRITICAL")pushEvent("RISK","Hazard CRITICAL threshold crossed","CRITICAL");
    else if(dangerLevel==="WARNING"&&prevDanger.current==="SAFE")pushEvent("RISK","Hazard elevated to WARNING","WARNING");
    else if(dangerLevel==="SAFE"&&prevDanger.current!=="SAFE")pushEvent("RISK","Hazard returned to SAFE","SUCCESS");
    prevDanger.current=dangerLevel;
  },[dangerLevel,data.risk]);

  useEffect(()=>{if(anomScore>0.6)pushEvent("ANOMALY",`Ensemble score ${(anomScore*100).toFixed(0)}% — ${data.anomaly?.severity}`,anomScore>0.75?"CRITICAL":"WARNING");},[Math.round(anomScore*10)]);
  useEffect(()=>{if(watchdogState==="STALE")pushEvent("WATCHDOG","No frames received > 3s","CRITICAL");if(watchdogState==="SLOW")pushEvent("WATCHDOG",`Pipeline ${pipelineMs.toFixed(0)}ms > 200ms budget`,"WARNING");},[watchdogState]);
  useEffect(()=>{if(ensemble.diversity_rescued)pushEvent("ENSEMBLE","Diversity rescue triggered — weights rebalanced","WARNING");},[ensemble.diversity_rescued]);
  useEffect(()=>{if(temporal.break)pushEvent("TEMPORAL","Pattern break detected — LSTM sequence disrupted","WARNING");},[temporal.break]);

  /* ── History chart ─────────────────────────────────────── */
  useEffect(()=>{
    if(data.risk)setHistory(prev=>[...prev.slice(-60),{t:new Date().toLocaleTimeString("en-US",{hour12:false}),hazard:hazard*100,anomaly:anomScore*100,composite:(data.decision?.composite_score??0)*100}]);
  },[data.risk?.hazard]);

  /* ── Audio alert ────────────────────────────────────────── */
  useEffect(()=>{
    if(dangerLevel==="CRITICAL"&&prevDanger.current!=="CRITICAL"){
      try{
        const actx=new(window.AudioContext||window.webkitAudioContext)();
        [[660,0],[880,0.15],[660,0.3],[1000,0.45]].forEach(([f,d])=>{
          const o=actx.createOscillator(),g=actx.createGain();
          o.connect(g);g.connect(actx.destination);o.frequency.value=f;g.gain.value=0.09;
          o.start(actx.currentTime+d);o.stop(actx.currentTime+d+0.12);
        });
      }catch{}
    }
  },[dangerLevel]);

  /* ── Scenario handler ───────────────────────────────────── */
  const handleSimulate=useCallback(async(scenario)=>{
    if(scenario.id==="clear"){setActiveScenario(null);pushEvent("SIMULATION","Scenarios cleared","SUCCESS");return;}
    setActiveScenario(scenario.id);pushEvent("SIMULATION",`Injected: ${scenario.label}  ${scenario.desc}`,"CAUTION");
    try{await fetch(`${SIM_URL}${scenario.endpoint}`);}catch{}
    setTimeout(()=>{setActiveScenario(null);pushEvent("SIMULATION","Scenario cleared","SUCCESS");},10000);
  },[pushEvent]);

  /* ─── RENDER ─────────────────────────────────────────────── */
  return(
    <>
      <style>{STYLES}</style>
      <RoadBg isCritical={dangerLevel==="CRITICAL"}/>
      <div style={{position:"fixed",left:0,width:"100%",height:"2px",zIndex:999,pointerEvents:"none",background:"linear-gradient(transparent,rgba(0,200,255,0.035),transparent)",animation:"scanV 7s linear infinite"}}/>

      <div style={{position:"relative",zIndex:1,minHeight:"100vh",padding:"14px 18px",color:T.text,fontFamily:"'Orbitron',monospace",filter:dangerLevel==="CRITICAL"?"brightness(1.05)":"brightness(1)"}}>

        {/* ═══ HEADER ═══ */}
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:"8px"}}>
          <div>
            <div style={{fontSize:"15px",fontWeight:900,color:T.amber,letterSpacing:"0.08em",textShadow:`0 0 18px ${T.amberGlow}`,marginBottom:"2px"}}>
              {activeScenario&&<span style={{fontSize:"9px",color:T.danger,marginRight:"10px",animation:"blink 0.8s infinite"}}>⚡ SIM</span>}
              ◈ COGNITIVE VEHICLE INTELLIGENCE SYSTEM
            </div>
            <div style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",letterSpacing:"0.1em"}}>CVIS v5.0 · Ensemble + Memory + Temporal · {new Date().toLocaleTimeString()}</div>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:"8px",flexWrap:"wrap",justifyContent:"flex-end"}}>
            <div style={{display:"flex",alignItems:"center",gap:"5px",padding:"5px 9px",borderRadius:"4px",background:wsConnected?`${T.success}10`:`${T.danger}10`,border:`1px solid ${wsConnected?T.success:T.danger}40`}}>
              <div style={{width:"6px",height:"6px",borderRadius:"50%",background:wsConnected?T.success:T.danger,animation:wsConnected?"pulse 2s infinite":"none"}}/>
              <span style={{fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",color:wsConnected?T.success:T.danger}}>{wsConnected?"WS LIVE":"WS RETRY"}</span>
            </div>
            <div style={{padding:"5px 9px",borderRadius:"4px",background:watchdogState==="OK"?`${T.success}10`:watchdogState==="SLOW"?`${T.warning}10`:`${T.danger}10`,border:`1px solid ${watchdogState==="OK"?T.success:watchdogState==="SLOW"?T.warning:T.danger}40`,fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",color:watchdogState==="OK"?T.success:watchdogState==="SLOW"?T.warning:T.danger}}>⟳ {watchdogState}</div>
            <button onClick={()=>exportDataset(frameBuffer.current)} style={{padding:"5px 10px",borderRadius:"4px",background:`${T.purple}15`,border:`1px solid ${T.purple}60`,color:T.purple,fontSize:"8px",fontFamily:"'Orbitron',monospace",fontWeight:700}}>⬇ EXPORT {frameBuffer.current.length}F</button>
            {[{l:"SPEED",v:`${speed.toFixed(0)}mph`},{l:"CONF",v:`${(confidence*100).toFixed(0)}%`},{l:"TEMP",v:`${thermal.toFixed(1)}°`,a:thermal>85},{l:"ANOM",v:`${(anomScore*100).toFixed(0)}%`,a:anomScore>0.5},{l:"PIPE",v:`${pipelineMs.toFixed(0)}ms`,a:pipelineMs>200},{l:"HEALTH",v:`${systemHealth.toFixed(0)}%`,a:systemHealth<50}].map(({l,v,a})=>(
              <div key={l} style={{textAlign:"center"}}>
                <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>{l}</div>
                <div style={{fontSize:"12px",fontWeight:700,color:a?T.danger:T.amber,animation:a?"pulse 1s infinite":"none"}}>{v}</div>
              </div>
            ))}
            <div style={{display:"flex",alignItems:"center",gap:"7px",padding:"6px 13px",borderRadius:"4px",background:`${color}12`,border:`1px solid ${color}70`,animation:dangerLevel==="CRITICAL"?"critFlash 1.5s infinite":"none"}}>
              <div style={{width:"6px",height:"6px",borderRadius:"50%",background:color,animation:"pulse 1.5s infinite"}}/>
              <span style={{fontSize:"11px",fontWeight:700,color,letterSpacing:"0.1em"}}>{dangerLevel}</span>
            </div>
          </div>
        </div>

        {/* ═══ SYSTEM MODE BANNER ═══ */}
        <SystemModeBanner dangerLevel={dangerLevel} watchdogState={watchdogState} systemHealth={systemHealth} failsafe={failsafe}/>

        {/* ═══ 7-COLUMN GRID ═══ */}
        <div style={{display:"grid",gridTemplateColumns:"220px 1fr 1fr 220px 220px 220px 220px",gap:"10px",alignItems:"start"}}>

          {/* ── COL 1: Camera + Telemetry + Thinking ── */}
          <div style={{display:"flex",flexDirection:"column",gap:"10px"}}>
            <Sec title="Live Vision Feed" alert={dangerLevel==="CRITICAL"}>
              {camError
                ?<div style={{height:"145px",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",background:"rgba(0,0,0,0.4)",borderRadius:"4px",fontSize:"10px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}><div style={{fontSize:"22px",marginBottom:"8px"}}>⊘</div>CAMERA UNAVAILABLE<div style={{fontSize:"8px",marginTop:"4px"}}>Signals-only mode</div></div>
                :<div style={{position:"relative",borderRadius:"6px",overflow:"hidden",border:`1px solid ${dangerLevel==="CRITICAL"?`${T.danger}60`:T.border}`,background:"#000"}}>
                  <video ref={videoRef} autoPlay muted playsInline style={{width:"100%",display:"block"}}/>
                  <canvas ref={overlayRef} style={{position:"absolute",top:0,left:0,width:"100%",height:"100%",pointerEvents:"none"}}/>
                  <div style={{position:"absolute",top:"8px",left:"50%",transform:"translateX(-50%)",fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",color:wsConnected?T.success:T.amber,animation:wsConnected?"pulse 2s infinite":"none"}}>{wsConnected?"◉ WS LIVE":"◉ POLLING"}</div>
                </div>}
              {objects.length>0&&<div style={{marginTop:"6px",display:"flex",gap:"5px",flexWrap:"wrap"}}>{objects.map((o,i)=><div key={i} style={{padding:"3px 7px",borderRadius:"3px",background:`${o.label==="PERSON"?T.warning:T.cyan}12`,border:`1px solid ${o.label==="PERSON"?T.warning:T.cyan}30`,fontSize:"8px",color:o.label==="PERSON"?T.warning:T.cyan,fontFamily:"'IBM Plex Mono',monospace"}}>{o.label} {o.conf!=null?(o.conf*100).toFixed(0):"-"}%{o.distance?` ${o.distance.toFixed(1)}m`:""}</div>)}</div>}
              <div style={{marginTop:"6px"}}><DepthCalibIndicator depthCalib={depthCalib}/></div>
            </Sec>

            <Sec title="Sensor Telemetry" compact>
              <SensorBar label="ENGINE TEMP" value={thermal}    max={120} unit="°C"  color={thermal>90?T.danger:thermal>75?T.warning:T.success}/>
              <SensorBar label="VIBRATION"   value={vibration}  max={60}  unit=" Hz" color={vibration>35?T.danger:T.amber}/>
              <SensorBar label="OIL PRESSURE" value={features.oil_pressure??65}  max={100} unit=" PSI" color={T.cyan}/>
              <SensorBar label="BATTERY"      value={((features.battery_voltage??13.8)/14.8)*100} max={100} unit="%" color={T.success}/>
              <SensorBar label="FUEL"         value={(features.fuel_level??0.68)*100} max={100} unit="%" color={(features.fuel_level??0.68)<0.2?T.danger:T.amber}/>
            </Sec>

            <Sec title="AI Thinking Flow" accent={T.purple} badge={{text:`${chain.length} STEPS`,color:T.purple}}>
              <AIThinkingFlow chain={chain}/>
            </Sec>
          </div>

          {/* ── COL 2: Risk + Gauges + Chart + Components ── */}
          <div style={{display:"flex",flexDirection:"column",gap:"10px"}}>
            <Sec title="Risk Assessment Core" alert={dangerLevel==="CRITICAL"} accent={color}>
              <HazardOrb hazard={hazard} dangerLevel={dangerLevel} color={color}/>
              <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:"4px",marginTop:"12px",justifyItems:"center"}}>
                <CircleGauge value={speed} max={120} label="SPEED" color={T.amber} size={76} unit="mph"/>
                <CircleGauge value={(features.rpm??0)/80} max={100} label="RPM×100" color={T.cyan} size={76}/>
                <CircleGauge value={confidence*100} max={100} label="AI CONF" color={T.success} size={76}/>
                <CircleGauge value={thermal} max={120} label="ENG °C" color={thermal>90?T.danger:T.warning} size={76} unit="°C"/>
                <CircleGauge value={anomScore*100} max={100} label="ANOMALY" color={anomScore>0.5?T.danger:T.warning} size={76}/>
              </div>
            </Sec>

            <Sec title="Hazard · Anomaly · Decision History" compact>
              <div style={{height:"110px"}}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history}>
                    <defs>
                      <linearGradient id="gH" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={0.35}/><stop offset="100%" stopColor={color} stopOpacity={0}/></linearGradient>
                      <linearGradient id="gA" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={T.warning} stopOpacity={0.2}/><stop offset="100%" stopColor={T.warning} stopOpacity={0}/></linearGradient>
                      <linearGradient id="gC" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={T.cyan} stopOpacity={0.2}/><stop offset="100%" stopColor={T.cyan} stopOpacity={0}/></linearGradient>
                    </defs>
                    <XAxis dataKey="t" stroke={T.muted} fontSize={7} tick={{fontFamily:"'IBM Plex Mono',monospace"}}/>
                    <YAxis stroke={T.muted} fontSize={7} tick={{fontFamily:"'IBM Plex Mono',monospace"}}/>
                    <Area type="monotone" dataKey="hazard"    stroke={color}    fill="url(#gH)" strokeWidth={2} dot={false}/>
                    <Area type="monotone" dataKey="anomaly"   stroke={T.warning} fill="url(#gA)" strokeWidth={1.5} dot={false} strokeDasharray="3 2"/>
                    <Area type="monotone" dataKey="composite" stroke={T.cyan}   fill="url(#gC)" strokeWidth={1.5} dot={false} strokeDasharray="4 3"/>
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Sec>

            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"10px"}}>
              <Sec title="Proximity Radar" compact>
                <div style={{display:"flex",justifyContent:"center"}}><ProximityRadar hazard={hazard} objects={objects}/></div>
                <div style={{marginTop:"6px",fontSize:"8px",fontFamily:"'IBM Plex Mono',monospace",color:hazard>0.6?T.danger:T.muted,textAlign:"center",animation:hazard>0.6?"pulse 1s infinite":"none"}}>{hazard>0.6?"⚠ PROXIMITY ALERT":"ZONE CLEAR"}</div>
              </Sec>
              <Sec title="Sensor Staleness" accent={T.cyan}>
                <SensorStalenessPanel staleness={staleness} obdConnected={obdConnected} imuConnected={imuConnected} gpsConnected={gpsConnected}/>
              </Sec>
            </div>

            <Sec title="Vehicle Component Health" alert={issues.length>0}>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:"6px"}}>
                {[{label:"ENGINE",icon:"⚙",key:"engine"},{label:"TRANSM",icon:"⟳",key:"transmission"},{label:"BRAKES F",icon:"⬛",key:"brakes_front"},{label:"BRAKES R",icon:"⬛",key:"brakes_rear"},{label:"TIRE FL",icon:"○",key:"tire_fl"},{label:"TIRE FR",icon:"○",key:"tire_fr"},{label:"TIRE RL",icon:"○",key:"tire_rl"},{label:"TIRE RR",icon:"○",key:"tire_rr"},{label:"SUSPENS",icon:"↕",key:"suspension"},{label:"STEERING",icon:"◎",key:"steering"},{label:"BATTERY",icon:"⚡",key:"battery"},{label:"COOLING",icon:"≋",key:"cooling"}].map(({label,icon,key})=>{
                  const health=compHealth[key]??80;
                  const iss=issues.find(i=>i.component?.toLowerCase().includes(label.toLowerCase().split(" ")[0]));
                  return <CompItem key={key} label={label} health={health} icon={icon} issue={iss?.issue}/>;
                })}
              </div>
            </Sec>
          </div>

          {/* ── COL 3: Decision + Anomaly + Latency ── */}
          <div style={{display:"flex",flexDirection:"column",gap:"10px"}}>
            <Sec title="Autonomous Decision Engine" accent={data.decision?.color||T.success} alert={data.decision?.urgency==="CRITICAL"} badge={{text:"HYSTERESIS·FIX4",color:T.cyan}}>
              <DecisionPanel decision={data.decision}/>
            </Sec>
            <Sec title="Anomaly Intelligence" accent={anomScore>0.5?T.danger:T.warning} alert={anomScore>0.65} badge={{text:"IF·AE·LSTM",color:T.purple}}>
              <AnomalyPanel anomaly={data.anomaly}/>
            </Sec>
            <Sec title="Pipeline Latency" accent={T.cyan} badge={{text:`${pipelineMs.toFixed(0)}ms`,color:pipelineMs>200?T.danger:T.success}}>
              <LatencyPanel latency={data.latency} pipelineMs={pipelineMs} watchdogState={watchdogState}/>
            </Sec>
          </div>

          {/* ── COL 4: NEW Panels ── */}
          <div style={{display:"flex",flexDirection:"column",gap:"10px"}}>
            {/* PANEL 1: Future Risk Prediction */}
            <Sec title="Future Risk Prediction" accent={T.danger} badge={{text:"PREDICTIVE",color:T.danger}}>
              <FutureRiskPanel futureRisk={futureRisk} adjustedScore={adjustedScore} memoryData={memoryData}/>
            </Sec>

            {/* PANEL 2: Memory / Trend */}
            <Sec title="Memory Trend" accent={T.purple} badge={{text:"30F WINDOW",color:T.purple}}>
              <MemoryTrendPanel history={history}/>
            </Sec>

            {/* PANEL 3: Validation */}
            <Sec title="Validation Metrics" accent={T.purple} badge={{text:"LIVE",color:T.purple}}>
              <ValidationPanel metrics={validMetrics}/>
            </Sec>
          </div>

          {/* ── COL 5: Ensemble + Trust ── */}
          <div style={{display:"flex",flexDirection:"column",gap:"10px"}}>
            {/* PANEL 4: Ensemble Transparency */}
            <Sec title="Ensemble Transparency" accent={T.cyan} badge={{text:"3-MODEL",color:T.cyan}}>
              <EnsemblePanel ensemble={ensemble} anomaly={data.anomaly}/>
            </Sec>

            {/* PANEL 5: Uncertainty / Trust */}
            <Sec title="System Trust" accent={T.success} badge={{text:"META-AI",color:T.success}}>
              <TrustPanel intelligence={data.intelligence} ensemble={ensemble} decision={data.decision}/>
            </Sec>

            {/* PANEL 6: Action Impact */}
            <Sec title="Action Impact" accent={data.decision?.color||T.success} badge={{text:"EXPLAIN",color:T.amber}}>
              <ActionImpactPanel decision={data.decision} speed={speed} ttc={ttc}/>
            </Sec>
          </div>

          {/* ── COL 6: Driver + Road + Learning ── */}
          <div style={{display:"flex",flexDirection:"column",gap:"10px"}}>
            <Sec title="Driver Behavior" accent={T.purple} badge={{text:"COGNITIVE",color:T.purple}} alert={(driver.fatigue_level??0)>0.5}>
              <DriverBehaviorPanel driver={driver}/>
            </Sec>
            <Sec title="Road Intelligence" accent={T.amber}>
              <div>
                {[{l:"SURFACE",v:roadCond.surface||"DRY",c:{DRY:T.success,WET:T.warning,ICY:T.danger,SNOW:T.cyan,GRAVEL:T.amber}[roadCond.surface||"DRY"]||T.muted},{l:"CURVATURE",v:`κ${(roadCond.curvature||0).toFixed(2)}`,c:(roadCond.curvature||0)>0.6?T.warning:T.cyan}].map(({l,v,c})=>(
                  <div key={l} style={{display:"inline-block",width:"48%",marginRight:"4%",padding:"8px 10px",background:"rgba(0,0,0,0.3)",borderRadius:"4px",border:`1px solid ${c}30`,marginBottom:"8px"}}>
                    <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>{l}</div>
                    <div style={{fontSize:"13px",color:c,fontFamily:"'Orbitron',monospace",fontWeight:700}}>{v}</div>
                  </div>
                ))}
                {[{l:"FRICTION μ",v:roadCond.friction??0.82,max:1,c:(roadCond.friction??0.82)<0.4?T.danger:(roadCond.friction??0.82)<0.65?T.warning:T.success},{l:"FOLLOWING DIST",v:roadCond.following_dist??3,max:6,c:(roadCond.following_dist??3)<2?T.danger:(roadCond.following_dist??3)<3?T.warning:T.success,unit:"s"},{l:"POTHOLE RISK",v:roadCond.pothole_risk??0.1,max:1,c:(roadCond.pothole_risk??0.1)>0.6?T.danger:T.amber,scale:100}].map(({l,v,max,c,scale,unit})=>(
                  <div key={l} style={{marginBottom:"8px"}}>
                    <div style={{display:"flex",justifyContent:"space-between",fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"3px"}}>
                      <span style={{color:T.muted}}>{l}</span>
                      <span style={{color:c,fontWeight:500}}>{scale?(v*scale).toFixed(0)+"%":v.toFixed(2)+(unit||"")}</span>
                    </div>
                    <div style={{height:"4px",borderRadius:"2px",background:"rgba(0,0,0,0.5)",overflow:"hidden"}}>
                      <div style={{width:`${(v/max)*100}%`,height:"100%",background:c,transition:"width 0.6s ease"}}/>
                    </div>
                  </div>
                ))}
                <div style={{padding:"7px 10px",borderRadius:"4px",background:"rgba(0,0,0,0.3)",border:`1px solid ${T.border}`,display:"flex",justifyContent:"space-between",fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",marginBottom:"7px"}}>
                  <span style={{color:T.muted}}>STOPPING DIST</span>
                  <span style={{color:T.amber}}>{((speed*speed)/(254*(roadCond.friction??0.82))).toFixed(1)}m</span>
                </div>
              </div>
            </Sec>
            <Sec title="Learning & Patterns" accent={T.purple} badge={{text:"ADAPTIVE",color:T.purple}}>
              <div>
                <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"8px"}}>{(data.learning?.patterns||[]).length} BEHAVIORAL PATTERNS LEARNED</div>
                {(data.learning?.patterns||[{pattern:"Aggressive braking — wet roads",freq:7,severity:"HIGH",learned:"2h ago"},{pattern:"Suspension stress — high RPM",freq:4,severity:"MEDIUM",learned:"45m ago"},{pattern:"Battery drain — cold start",freq:12,severity:"LOW",learned:"1d ago"}]).map((p,i)=>{
                  const c=p.severity==="HIGH"?T.danger:p.severity==="MEDIUM"?T.warning:T.cyan;
                  return(<div key={i} style={{padding:"8px 11px",borderRadius:"4px",background:"rgba(0,0,0,0.3)",borderLeft:`2px solid ${c}`,marginBottom:"6px"}}>
                    <div style={{display:"flex",justifyContent:"space-between",marginBottom:"2px"}}>
                      <div style={{fontSize:"10px",color:T.text,fontFamily:"'IBM Plex Mono',monospace"}}>{p.pattern}</div>
                      <div style={{fontSize:"8px",color:c,fontFamily:"'IBM Plex Mono',monospace",whiteSpace:"nowrap",marginLeft:"8px"}}>{p.severity}</div>
                    </div>
                    <div style={{display:"flex",justifyContent:"space-between",fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>
                      <span>×{p.freq}</span><span>{p.learned}</span>
                    </div>
                  </div>);
                })}
              </div>
            </Sec>
          </div>

          {/* ── COL 7: Events + Advisories + Simulation + Predictions ── */}
          <div style={{display:"flex",flexDirection:"column",gap:"10px"}}>
            <Sec title="AI Advisories" alert={advisories.some(a=>a.sev==="CRITICAL")}>
              {advisories.length===0
                ?<div style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>All systems nominal.</div>
                :advisories.map((a,i)=><Advisory key={i} text={typeof a==="string"?a:a.text} sev={typeof a==="object"?a.sev:"INFO"} idx={i}/>)}
            </Sec>
            <Sec title="Event Log" badge={{text:`${events.filter(e=>e.severity==="CRITICAL").length} CRIT`,color:T.danger}}>
              <EventLogPanel events={events}/>
            </Sec>
            <Sec title="Scenario Simulation" accent={T.danger} badge={{text:"INJECT",color:T.danger}}>
              <SimulationControl onSimulate={handleSimulate} activeScenario={activeScenario}/>
            </Sec>
            <Sec title="Predictive Maintenance" alert={predictions.some(p=>p.severity>0.7)} compact>
              {predictions.length===0
                ?<div style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>No predictions.</div>
                :predictions.map((p,i)=>{
                  const c=p.severity>0.7?T.danger:p.severity>0.4?T.warning:T.amber;
                  return(<div key={i} style={{padding:"9px 11px",borderRadius:"4px",background:"rgba(0,0,0,0.3)",border:`1px solid ${c}30`,marginBottom:"6px"}}>
                    <div style={{display:"flex",justifyContent:"space-between",marginBottom:"4px"}}>
                      <div style={{fontSize:"10px",fontFamily:"'IBM Plex Mono',monospace",color:T.text,fontWeight:500}}>{p.type}</div>
                      <div style={{fontSize:"9px",fontFamily:"'IBM Plex Mono',monospace",color:c}}>{p.time_to_risk}</div>
                    </div>
                    <div style={{fontSize:"8px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"4px"}}>{p.component}</div>
                    <div style={{height:"3px",borderRadius:"2px",background:"rgba(0,0,0,0.4)",overflow:"hidden"}}>
                      <div style={{width:`${p.severity*100}%`,height:"100%",background:c,transition:"width 0.8s ease"}}/>
                    </div>
                  </div>);
                })}
            </Sec>
            <Sec title="Dataset Export" accent={T.purple} compact>
              <div style={{fontSize:"9px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace",marginBottom:"8px"}}>Logging {frameBuffer.current.length} frames → JSONL</div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"6px",marginBottom:"8px"}}>
                {[{l:"FRAMES",v:frameBuffer.current.length,c:T.cyan},{l:"DECISIONS",v:validRef.current?.log?.length??0,c:T.success}].map(({l,v,c})=>(
                  <div key={l} style={{padding:"6px",textAlign:"center",background:`${c}08`,borderRadius:"4px",border:`1px solid ${c}25`}}>
                    <div style={{fontSize:"7px",color:T.muted,fontFamily:"'IBM Plex Mono',monospace"}}>{l}</div>
                    <div style={{fontSize:"14px",fontWeight:700,color:c,fontFamily:"'Orbitron',monospace"}}>{v}</div>
                  </div>
                ))}
              </div>
              <button onClick={()=>exportDataset(frameBuffer.current)} style={{width:"100%",padding:"8px",borderRadius:"4px",background:`${T.purple}15`,border:`1px solid ${T.purple}50`,color:T.purple,fontSize:"9px",fontFamily:"'Orbitron',monospace",fontWeight:700}}>⬇ EXPORT JSONL DATASET</button>
            </Sec>
          </div>

        </div>
      </div>
      <canvas ref={canvasRef} style={{display:"none"}}/>
    </>
  );
}
