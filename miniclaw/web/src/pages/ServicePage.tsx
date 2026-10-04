import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowDownLeft,
  ArrowRight,
  Building2,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Clock3,
  Cog,
  MessageSquare,
  Plus,
  Search,
  Wind,
  Wrench,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  companies,
  createDemoTickets,
  devices,
  statusTone,
  type Ticket,
  type TicketStatus,
} from '../features/service/demo-data';
import '../styles/service.css';
import { AgentDesk, type RepairDraft } from '../features/service/AgentDesk';

type Section = 'agent' | 'tickets' | 'devices' | 'maintenance' | 'events';
const sections = [
  { id: 'agent', label: 'Agent 工作台', icon: MessageSquare },
  { id: 'tickets', label: '报修与工单', icon: ClipboardList },
  { id: 'devices', label: '设备台账', icon: Cog },
  { id: 'maintenance', label: '保养计划', icon: Wrench },
  { id: 'events', label: '处理记录', icon: Activity },
] as const;
const statuses: TicketStatus[] = ['待确认', '待处理', '处理中', '已完成'];

export function ServicePage() {
  const [section, setSection] = useState<Section>('agent');
  const [company, setCompany] = useState<string>(companies[1]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [tickets, setTickets] = useState(createDemoTickets);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [repairOpen, setRepairOpen] = useState(false);
  const [deviceId, setDeviceId] = useState('');
  const [symptom, setSymptom] = useState('');
  const [priority, setPriority] = useState<Ticket['priority']>('普通');
  const [confirmed, setConfirmed] = useState(false);
  const [notice, setNotice] = useState('');
  const scopedDevices = devices.filter(
    (d) => company === 'all' || d.company === company,
  );
  const scopedTickets = tickets.filter(
    (t) => company === 'all' || t.company === company,
  );
  const selected = scopedTickets.find((t) => t.id === selectedId);
  const selectedDevice = devices.find((d) => d.id === selected?.deviceId);
  const formDevice = scopedDevices.find((d) => d.id === deviceId);
  const visibleTickets = scopedTickets.filter(
    (t) =>
      (status === 'all' || t.status === status) &&
      `${t.id} ${t.title} ${t.deviceId} ${t.company}`
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );
  const events = useMemo(
    () =>
      scopedTickets.flatMap((t) =>
        t.events.map((event, i) => ({
          ...event,
          ticket: t,
          key: `${t.id}-${i}`,
        })),
      ),
    [scopedTickets],
  );

  function openRepair(id = '') {
    setDeviceId(id);
    setSymptom('');
    setPriority('普通');
    setConfirmed(false);
    setNotice('');
    setRepairOpen(true);
  }
  function createAgentRepair({
    device,
    symptom,
    priority,
  }: RepairDraft): Ticket {
    const duplicate = tickets.find(
      (t) =>
        t.deviceId === device.id &&
        t.title === symptom.trim() &&
        t.status !== '已完成',
    );
    if (duplicate) return duplicate;
    const now = new Date().toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
    const ticket: Ticket = {
      id: `DEMO-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
      company: device.company,
      deviceId: device.id,
      title: symptom.trim(),
      priority,
      status: '待处理',
      source: '工作台',
      createdAt: now,
      events: [
        {
          time: now,
          title: 'Agent 报修信息已确认（演示）',
          detail: `${device.company} · ${device.id} · ${symptom.trim()}`,
        },
        {
          time: now,
          title: '生成演示工单',
          detail: '仅在当前页面创建；未调用后端，未发送飞书通知。',
        },
      ],
    };
    setTickets((current) => [ticket, ...current]);
    return ticket;
  }
  function changeCompany(value: string) {
    setCompany(value);
    setSelectedId(null);
    setRepairOpen(false);
    setDeviceId('');
    setSymptom('');
    setConfirmed(false);
    setQuery('');
    setStatus('all');
    setNotice('');
  }
  function saveRepair(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!formDevice || !confirmed || !symptom.trim()) return;
    const duplicate = tickets.find(
      (t) =>
        t.deviceId === deviceId &&
        t.title === symptom.trim() &&
        t.status !== '已完成',
    );
    if (duplicate) {
      setNotice('当前设备已有相同的未完成报修，已为你打开该记录。');
      setRepairOpen(false);
      setSelectedId(duplicate.id);
      return;
    }
    const now = new Date().toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
    const ticket: Ticket = {
      id: `DEMO-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
      company: formDevice.company,
      deviceId,
      title: symptom.trim(),
      status: '待处理',
      source: '工作台',
      priority,
      createdAt: now,
      events: [
        {
          time: now,
          title: '设备与故障已确认',
          detail: `${formDevice.company} · ${deviceId}`,
        },
        {
          time: now,
          title: '已生成演示报修',
          detail: '仅保存在当前页面，未提交到售后系统，也未发送飞书通知。',
        },
      ],
    };
    setTickets((current) => [ticket, ...current]);
    setRepairOpen(false);
    setSelectedId(ticket.id);
    setNotice('演示报修已生成；刷新页面后将恢复示例数据。');
  }
  function confirmDevice(ticket: Ticket) {
    setTickets((current) =>
      current.map((t) =>
        t.id === ticket.id && t.status === '待确认'
          ? {
              ...t,
              status: '待处理',
              events: [
                ...t.events,
                {
                  time: '刚刚',
                  title: '用户确认设备（演示）',
                  detail: `${t.deviceId} · 报修信息已补齐，等待处理。`,
                },
              ],
            }
          : t,
      ),
    );
  }
  const ticketTable = (compact = false) => (
    <div className="fy-table-wrap">
      <table className="fy-table">
        <thead>
          <tr>
            <th>工单 / 报修内容</th>
            <th>设备与企业</th>
            <th>来源</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>
              <span className="sr-only">操作</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {(compact ? scopedTickets.slice(0, 4) : visibleTickets).map((t) => (
            <tr key={t.id}>
              <td>
                <button
                  className="fy-ticket-link"
                  onClick={() => setSelectedId(t.id)}
                >
                  {t.title}
                </button>
                <small>
                  {t.id}
                  {t.priority === '紧急' && (
                    <span className="fy-urgent">紧急</span>
                  )}
                </small>
              </td>
              <td>
                <span className="fy-mono">{t.deviceId}</span>
                <small>{t.company}</small>
              </td>
              <td>
                <span className="fy-source">
                  <MessageSquare size={13} />
                  {t.source}
                </span>
              </td>
              <td>
                <span className={`fy-tag ${statusTone[t.status]}`}>
                  <i />
                  {t.status}
                </span>
              </td>
              <td className="fy-time">{t.createdAt}</td>
              <td>
                <button
                  className="fy-icon-button"
                  aria-label={`查看工单 ${t.id}`}
                  onClick={() => setSelectedId(t.id)}
                >
                  <ChevronRight size={17} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!compact && visibleTickets.length === 0 && (
        <div className="fy-empty">
          <Search size={26} />
          <strong>没有找到匹配的工单</strong>
          <p>试试其他设备编号、关键词或处理状态。</p>
          <button
            className="fy-button"
            onClick={() => {
              setQuery('');
              setStatus('all');
            }}
          >
            清除筛选
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className="fy-service">
      <header className="fy-topbar">
        <button
          onClick={() => setSection('agent')}
          className="fy-brand"
          aria-label="空压机售后首页"
        >
          <span className="fy-brand-icon">
            <Wind size={25} />
          </span>
          <span>
            <b>空压机售后</b>
          </span>
        </button>
        <div className="fy-topbar-right">
          <span className="fy-environment">演示工作台</span>
          <Link to="/chat" className="fy-console-link">
            真实会话入口 <ArrowRight size={14} />
          </Link>
          <span className="fy-avatar" aria-hidden="true">
            售
          </span>
        </div>
      </header>

      <div className="fy-content">
        <div className="fy-page-heading">
          <div>
            <p className="fy-eyebrow">FENGYUN SERVICE AGENT</p>
            <h1>与 Agent 一起处理售后需求</h1>
            <p className="fy-subtitle">
              客户在飞书提需求，售后在这里跟进任务、确认信息与接手处理。
            </p>
          </div>
          <button className="fy-button" onClick={() => openRepair()}>
            <Plus size={17} />
            新建报修
          </button>
        </div>
        <div className="fy-demo-note">
          <CircleHelp size={15} />
          <span>
            前端演示 ·
            对话按本地规则模拟，未连接模型或飞书；工单和设备均为示例，刷新后重置。
          </span>
        </div>
        <div className="fy-navigation">
          <nav aria-label="售后业务导航">
            {sections.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                aria-current={section === id ? 'page' : undefined}
                className={section === id ? 'active' : ''}
                onClick={() => setSection(id)}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
          </nav>
          <label className="fy-company">
            <Building2 size={15} />
            <select
              aria-label="筛选演示企业"
              value={company}
              onChange={(e) => changeCompany(e.target.value)}
            >
              <option value="all">全部企业 · 演示</option>
              {companies.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>
        {notice && (
          <p className="fy-notice" role="status">
            <Check size={16} />
            {notice}
          </p>
        )}

        <div hidden={section !== 'agent'}>
          <AgentDesk
            key={company}
            company={company}
            devices={scopedDevices}
            tickets={scopedTickets}
            onCreateRepair={createAgentRepair}
            onViewTicket={setSelectedId}
          />
        </div>

        {section === 'tickets' && (
          <section className="fy-panel">
            <div className="fy-panel-heading">
              <div>
                <h2>
                  报修与工单{' '}
                  <span className="fy-count">{scopedTickets.length}</span>
                </h2>
                <p>待确认的报修先补齐信息，再进入处理队列</p>
              </div>
            </div>
            <div className="fy-filters">
              <label className="fy-search">
                <Search size={16} />
                <input
                  aria-label="搜索工单"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索工单、故障或设备编号"
                />
              </label>
              <select
                aria-label="工单状态"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="all">全部状态</option>
                {statuses.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
              <span>{visibleTickets.length} 条结果</span>
            </div>
            {ticketTable()}
          </section>
        )}

        {section === 'devices' && (
          <section className="fy-panel">
            <div className="fy-panel-heading">
              <div>
                <h2>设备台账</h2>
                <p>通过设备序列号确认唯一对象，避免同型号设备混淆</p>
              </div>
              <span className="fy-tag gray">{scopedDevices.length} 台设备</span>
            </div>
            <div className="fy-device-grid">
              {scopedDevices.map((d) => (
                <article className="fy-device-card" key={d.id}>
                  <div className="fy-device-top">
                    <span className="fy-machine">
                      <Wind size={34} />
                    </span>
                    <span className="fy-tag gray">{d.model}</span>
                  </div>
                  <h3>{d.name}</h3>
                  <p>{d.company}</p>
                  <dl>
                    <div>
                      <dt>序列号</dt>
                      <dd className="fy-mono">{d.id}</dd>
                    </div>
                    <div>
                      <dt>安装位置</dt>
                      <dd>{d.location}</dd>
                    </div>
                    <div>
                      <dt>关联记录</dt>
                      <dd>
                        {
                          scopedTickets.filter((t) => t.deviceId === d.id)
                            .length
                        }{' '}
                        条
                      </dd>
                    </div>
                  </dl>
                  <button
                    className="fy-button"
                    onClick={() => openRepair(d.id)}
                  >
                    为此设备报修 <ArrowRight size={14} />
                  </button>
                </article>
              ))}
            </div>
          </section>
        )}

        {section === 'maintenance' && (
          <section className="fy-panel">
            <div className="fy-panel-heading">
              <div>
                <h2>保养计划</h2>
                <p>依据设备型号与保养周期，查看临期、逾期及正常设备</p>
              </div>
              <span className="fy-tag gray">示例周期</span>
            </div>
            <div className="fy-maintenance-list">
              {scopedDevices.map((d) => (
                <article className="fy-maintenance" key={d.id}>
                  <div>
                    <span
                      className={`fy-tag ${d.maintenanceDays < 0 ? 'amber' : d.maintenanceDays <= 7 ? 'blue' : 'teal'}`}
                    >
                      {d.maintenanceDays < 0
                        ? `逾期 ${-d.maintenanceDays} 天`
                        : `${d.maintenanceDays} 天后到期`}
                    </span>
                    <h3>
                      {d.name} <span>{d.model}</span>
                    </h3>
                    <p>
                      {d.company} · {d.id}
                    </p>
                  </div>
                  <div>
                    <h4>对应型号的保养项目</h4>
                    <ul>
                      {d.maintenanceItems.map((item) => (
                        <li key={item}>
                          <Check size={13} />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                </article>
              ))}
            </div>
            <div className="fy-planned">
              <Clock3 size={19} />
              <div>
                <strong>自动保养提醒 · 规划中</strong>
                <p>
                  计划按周期扫描临期设备，经确认后安排保养。本页暂不发送提醒或自动派单。
                </p>
              </div>
            </div>
          </section>
        )}

        {section === 'events' && (
          <section className="fy-panel">
            <div className="fy-panel-heading">
              <div>
                <h2>处理记录</h2>
                <p>按工单关联原始需求、设备确认和处理结果；当前为演示记录</p>
              </div>
            </div>
            <div className="fy-event-list">
              {events.map((event) => (
                <div className="fy-event-row" key={event.key}>
                  <span className="fy-event-icon">
                    <ArrowDownLeft size={16} />
                  </span>
                  <div>
                    <strong>{event.title}</strong>
                    <p>{event.detail}</p>
                    <button
                      className="fy-text-button"
                      onClick={() => setSelectedId(event.ticket.id)}
                    >
                      {event.ticket.id}
                      <ChevronRight size={13} />
                    </button>
                  </div>
                  <time>{event.time}</time>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      <Dialog
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null);
        }}
      >
        <DialogContent className="fy-dialog sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>报修与工单详情</DialogTitle>
            <DialogDescription>演示记录 · {selected?.id}</DialogDescription>
          </DialogHeader>
          {selected && (
            <>
              <div className="fy-detail-title">
                <h2>{selected.title}</h2>
                <span className={`fy-tag ${statusTone[selected.status]}`}>
                  {selected.status}
                </span>
              </div>
              <dl className="fy-detail-fields">
                <div>
                  <dt>所属企业</dt>
                  <dd>{selected.company}</dd>
                </div>
                <div>
                  <dt>设备序列号</dt>
                  <dd>{selected.deviceId}</dd>
                </div>
                <div>
                  <dt>设备 / 位置</dt>
                  <dd>
                    {selectedDevice?.name} · {selectedDevice?.location}
                  </dd>
                </div>
                <div>
                  <dt>来源 / 优先级</dt>
                  <dd>
                    {selected.source} · {selected.priority}
                  </dd>
                </div>
              </dl>
              {selected.status === '待确认' && (
                <div className="fy-confirm-box">
                  <strong>请核对本次报修的设备</strong>
                  <p>确认设备后，此演示报修将进入待处理状态。</p>
                  <button
                    className="fy-button primary"
                    onClick={() => confirmDevice(selected)}
                  >
                    <Check size={15} />
                    确认是这台设备
                  </button>
                </div>
              )}
              <h3 className="fy-detail-subheading">处理过程</h3>
              <ol className="fy-timeline">
                {selected.events.map((event, i) => (
                  <li key={i}>
                    <span />
                    <div>
                      <strong>{event.title}</strong>
                      <p>{event.detail}</p>
                      <time>{event.time}</time>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="fy-detail-footnote">
                演示操作未写入售后系统，也未发送飞书通知。
              </p>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={repairOpen} onOpenChange={setRepairOpen}>
        <DialogContent className="fy-dialog">
          <DialogHeader>
            <DialogTitle>新建报修</DialogTitle>
            <DialogDescription>
              确认设备并补齐故障信息，生成本页面内的演示报修。
            </DialogDescription>
          </DialogHeader>
          <form className="fy-repair-form" onSubmit={saveRepair}>
            <label>
              选择设备
              <select
                required
                aria-label="选择报修设备"
                value={deviceId}
                onChange={(e) => {
                  setDeviceId(e.target.value);
                  setConfirmed(false);
                }}
              >
                <option value="">请选择具体设备</option>
                {scopedDevices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.company} · {d.id}
                  </option>
                ))}
              </select>
            </label>
            {formDevice && (
              <div className="fy-selected-device">
                <Wind size={24} />
                <div>
                  <strong>
                    {formDevice.name} · {formDevice.model}
                  </strong>
                  <p>
                    {formDevice.company} / {formDevice.location}
                  </p>
                </div>
              </div>
            )}
            <label>
              故障描述
              <textarea
                aria-label="故障描述"
                required
                maxLength={1000}
                rows={4}
                value={symptom}
                onChange={(e) => setSymptom(e.target.value)}
                placeholder="请描述出现的现象、报警代码和发生时间…"
              />
            </label>
            <label>
              优先级
              <select
                aria-label="报修优先级"
                value={priority}
                onChange={(e) =>
                  setPriority(e.target.value as Ticket['priority'])
                }
              >
                <option>普通</option>
                <option>紧急</option>
              </select>
            </label>
            <label className="fy-checkbox">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              我已核对企业、设备序列号和故障信息
            </label>
            <button
              type="submit"
              className="fy-button primary"
              disabled={!formDevice || !symptom.trim() || !confirmed}
            >
              <Plus size={16} />
              生成演示报修
            </button>
            <p className="fy-detail-footnote">
              仅在当前页面保留，刷新后重置；不会创建真实工单。
            </p>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
