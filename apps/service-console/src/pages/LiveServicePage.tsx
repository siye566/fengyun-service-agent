import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, ClipboardList, Database, MessageSquare, RefreshCw, ShieldCheck, Wind, Wrench } from 'lucide-react';
import './live-service.css';

type Result = { ok: boolean; data?: { stage?: string; clarification?: string[]; executed_tools?: string[]; results?: ToolResult[] }; error?: { message: string; action: string } };
type ToolResult = { ok: boolean; data?: { ticket_no?: string; advice?: string; status_text?: string; hint?: string; tickets?: { ticket_no: string; status_text: string }[] }; error?: { message: string } };
type Device = { serial_no: string; model: string; maintenance: { hint: string; next_due_date: string; days_left: number } };
type Ticket = { ticket_no: string; symptom: string; device_serial: string; status_text: string; created_at: string; advice: string };
type Snapshot = { csrf: string; company: string; devices: Device[]; tickets: Ticket[]; state: { stage: string; pending: { device_serial: string; symptom: string } | null }; history: { utterance: string; result: Result; created_at: string }[] };
type Payload = { action: string; event_id: string; utterance?: string; device_serial?: string; symptom?: string };

async function readJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求未通过校验，请检查输入');
  return data;
}
// Share bootstrap across StrictMode effects; simultaneous cookie creation must
// not leave the visible page referring to a different visitor than its cookie.
let bootstrap: Promise<Snapshot> | undefined;
function firstSession() {
  return bootstrap ??= readJson<Snapshot>('/api/session').catch(error => { bootstrap = undefined; throw error; });
}
function eventId() {
  // Public HTTP IP previews do not have crypto.randomUUID (secure contexts only).
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}
function reply(result: Result): string {
  if (!result.ok) return `${result.error?.message ?? '处理未完成'}。${result.error?.action ?? ''}`;
  const data = result.data!;
  const lines = [...(data.clarification ?? [])];
  for (const tool of data.results ?? []) {
    if (!tool.ok) { lines.push(tool.error?.message ?? '查询未完成'); continue; }
    const value = tool.data ?? {};
    if (value.ticket_no) lines.push(`工单 ${value.ticket_no} · ${value.status_text ?? '已受理'}`);
    if (value.advice) lines.push(value.advice);
    if (value.hint) lines.push(value.hint);
    if (value.tickets) lines.push(value.tickets.length ? value.tickets.map(t => `${t.ticket_no} · ${t.status_text}`).join('\n') : '当前体验空间还没有工单。');
  }
  if (data.stage === 'cancelled') lines.push('当前报修已取消。');
  return lines.join('\n') || '处理完成。';
}

export function LiveServicePage() {
  const [data, setData] = useState<Snapshot>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<'agent' | 'tickets' | 'devices'>('agent');
  const [utterance, setUtterance] = useState('');
  const [serial, setSerial] = useState('');
  const [symptom, setSymptom] = useState('');
  const [failed, setFailed] = useState<Payload>();
  const lock = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true;
    firstSession().then(value => { if (active) { setData(value); setSerial(value.devices[0]?.serial_no ?? ''); } })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [data?.history.length]);
  async function send(payload: Omit<Payload, 'event_id'> | Payload) {
    if (lock.current || !data) return;
    lock.current = true; setBusy(true); setError('');
    const request = { ...payload, event_id: 'event_id' in payload ? payload.event_id : eventId() } as Payload;
    try {
      const answer = await readJson<{ result: Result; snapshot: Snapshot }>('/api/turn', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': data.csrf }, body: JSON.stringify(request),
      });
      setData(answer.snapshot); setFailed(undefined); setUtterance('');
    } catch (e) { setError(e instanceof Error ? e.message : '连接失败'); setFailed(request); }
    finally { lock.current = false; setBusy(false); }
  }
  const pending = data?.state.pending;
  return <div className="live-app">
    <header className="live-header"><a href="/" className="live-brand"><span><Wind size={25} /></span><b>空压机售后<span>Service Workspace</span></b></a>
      <div className="live-header-links"><span className="live-connected"><i />PostgreSQL</span><a href="https://github.com/siye566/fengyun-service-agent" target="_blank" rel="noreferrer">查看源码 <ArrowRight size={14} /></a></div>
    </header>
    <main className="live-main">
      <div className="live-heading"><div><p>SERVICE OPERATIONS</p><h1>让每一次报修都有清晰的下一步</h1><span>确认设备、核对故障、跟踪工单。业务状态由服务端保存。</span></div><span className="live-badge"><ShieldCheck size={16} />独立体验空间</span></div>
      <div className="live-note"><Database size={17} /><span>使用合成设备与业务规则，不调用大模型或飞书。体验数据保留 24 小时；请使用示例故障完成流程。</span></div>
      <nav className="live-nav" aria-label="业务导航">{([{ id: 'agent', label: '服务工作台', icon: MessageSquare }, { id: 'tickets', label: '报修工单', icon: ClipboardList }, { id: 'devices', label: '设备与保养', icon: Wrench }] as const).map(item => <button key={item.id} className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)}><item.icon size={17} />{item.label}{item.id === 'tickets' && <small>{data?.tickets.length ?? 0}</small>}</button>)}
        <span>{data?.company ?? '正在连接服务…'}</span></nav>
      {error && <div className="live-error" role="alert">{error}<button onClick={() => window.location.reload()}>刷新页面</button>{failed && <button disabled={busy} onClick={() => send(failed)}>重试上一请求</button>}</div>}
      {!data && !error && <div className="live-panel live-loading">正在创建体验空间…</div>}
      {data && tab === 'agent' && <div className="live-workspace">
        <section className="live-panel live-chat"><div className="live-panel-title"><span className="live-agent-icon"><Wind size={22} /></span><div><h2>售后服务助手</h2><p>报修确认 · 进度查询 · 保养信息</p></div><span>业务规则模式</span></div>
          <div className="live-messages" role="log" aria-live="polite"><div className="live-message assistant"><small>服务助手</small><p>你好，先选择右侧设备并填写“机器异响”等示例故障，生成确认信息。你也可以在这里输入售后需求。</p></div>
            {data.history.map((entry, index) => <div key={index}><div className="live-message user"><small>你</small><p>{entry.utterance}</p></div><div className="live-message assistant"><small>服务助手</small><p>{reply(entry.result)}</p></div></div>)}<div ref={bottom} />
          </div>
          <div className="live-quick"><button disabled={busy} onClick={() => send({ action: 'progress' })}>查工单进度</button><button disabled={busy || !serial} onClick={() => send({ action: 'maintenance', device_serial: serial })}>查当前设备保养</button></div>
          <form className="live-compose" onSubmit={e => { e.preventDefault(); send({ action: 'message', utterance }); }}><textarea aria-label="售后需求" value={utterance} onChange={e => setUtterance(e.target.value)} maxLength={4000} placeholder="例如：查工单进度，或输入设备编号与故障" /><button disabled={busy || !utterance.trim()} className="live-primary" type="submit">{busy ? '处理中…' : '发送'}<ArrowRight size={15} /></button></form>
        </section>
        <aside className="live-side"><section className="live-panel"><div className="live-panel-title"><ClipboardList size={20} /><div><h2>报修信息</h2><p>先核对信息，确认后才建单</p></div></div>
          <form className="live-repair" onSubmit={e => { e.preventDefault(); send({ action: 'prepare_repair', device_serial: serial, symptom }); }}><label>选择设备<select aria-label="报修设备" value={serial} onChange={e => setSerial(e.target.value)}>{data.devices.map(d => <option key={d.serial_no} value={d.serial_no}>{d.model} · {d.serial_no}</option>)}</select></label><label>故障现象<textarea aria-label="故障现象" value={symptom} onChange={e => setSymptom(e.target.value)} maxLength={500} placeholder="例如：机器异响、不出气" /></label><button className="live-primary" disabled={busy || !symptom.trim() || !!pending}>核对报修信息<ArrowRight size={15} /></button></form>
        </section><section className="live-panel live-task"><h2>当前任务</h2>{pending ? <><span className="live-task-status">{data.state.stage === 'awaiting_details' ? '等待补充' : '等待确认'}</span><dl><dt>设备</dt><dd>{pending.device_serial || '待补充'}</dd><dt>故障</dt><dd>{pending.symptom || '待补充'}</dd></dl><button className="live-primary" disabled={busy || !['awaiting_confirmation', 'confirming'].includes(data.state.stage)} onClick={() => send({ action: 'confirm_repair' })}><Check size={16} />确认提交报修</button><button className="live-secondary" disabled={busy} onClick={() => send({ action: 'cancel_repair' })}>取消当前报修</button></> : <div className="live-empty"><Check size={24} /><p>{data.state.stage === 'completed' ? '报修已受理，可在工单页查看' : '暂无待确认报修'}</p><small>进度与保养查询不会覆盖当前任务</small></div>}</section></aside>
      </div>}
      {data && tab === 'tickets' && <section className="live-panel live-tickets"><div className="live-panel-title"><ClipboardList size={21} /><div><h2>报修工单</h2><p>只展示当前体验空间的记录；刷新后仍可查看</p></div><button disabled={busy} onClick={() => send({ action: 'progress' })}><RefreshCw size={16} />查询进度</button></div>{data.tickets.length ? data.tickets.map(ticket => <article className="live-ticket" key={ticket.ticket_no}><div><span>{ticket.ticket_no}</span><strong>{ticket.symptom}</strong><small>{ticket.device_serial} · {ticket.created_at}</small><p>{ticket.advice}</p></div><span className="live-task-status">{ticket.status_text}</span></article>) : <div className="live-empty"><ClipboardList size={30} /><p>还没有工单</p><button className="live-secondary" onClick={() => setTab('agent')}>返回工作台开始报修</button></div>}</section>}
      {data && tab === 'devices' && <div className="live-device-grid">{data.devices.map(device => <section className="live-panel live-device" key={device.serial_no}><span className="live-device-icon"><Wind size={40} /></span><h2>{device.model} 空压机</h2><p>{device.serial_no}</p><dl><dt>所属企业</dt><dd>{data.company}</dd><dt>下次保养</dt><dd>{device.maintenance.next_due_date}</dd></dl><div className="live-maintenance"><Wrench size={18} /><span>{device.maintenance.hint}</span></div><button className="live-secondary" disabled={busy} onClick={() => { setSerial(device.serial_no); setTab('agent'); send({ action: 'maintenance', device_serial: device.serial_no }); }}>查询保养信息<ArrowRight size={15} /></button></section>)}</div>}
      <footer className="live-footer">合成样例 · 企业作用域隔离 · 确认后写入 PostgreSQL</footer>
    </main>
  </div>;
}
