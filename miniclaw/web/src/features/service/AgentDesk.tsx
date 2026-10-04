import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Bot,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  CornerDownLeft,
  Hand,
  MessageSquare,
  Send,
  ShieldCheck,
  Wind,
  Wrench,
} from 'lucide-react';
import type { Device, Ticket } from './demo-data';
import './agent-desk.css';

type Kind = 'repair' | 'progress' | 'maintenance' | 'manual';
type Stage = 'device' | 'details' | 'review' | 'done' | 'manual';
interface Task {
  id: string;
  kind: Kind;
  stage: Stage;
  request: string;
  deviceId: string;
  symptom: string;
  ticketId?: string;
  result: string;
}
interface Message {
  id: string;
  role: 'user' | 'agent';
  text: string;
  ticketIds?: string[];
}
interface Trace {
  id: string;
  taskId: string;
  title: string;
  input: string;
  output: string;
}
interface Session {
  messages: Message[];
  tasks: Task[];
  traces: Trace[];
  activeId: string | null;
}
export interface RepairDraft {
  device: Device;
  symptom: string;
  priority: Ticket['priority'];
}
interface Props {
  company: string;
  devices: Device[];
  tickets: Ticket[];
  onCreateRepair: (draft: RepairDraft) => Ticket;
  onViewTicket: (id: string) => void;
}
const names: Record<Kind, string> = {
  repair: '故障报修',
  progress: '工单进度',
  maintenance: '保养查询',
  manual: '人工协助',
};
const stages: Record<Stage, string> = {
  device: '等待设备确认',
  details: '等待补充故障',
  review: '等待提交确认',
  done: '已完成演示',
  manual: '待人工接手',
};
let sequence = 0;
const id = () => `LOCAL-${++sequence}`;
const message = (
  text: string,
  role: Message['role'] = 'agent',
  ticketIds?: string[],
): Message => ({ id: id(), text, role, ticketIds });
const initialSession = (): Session => ({
  messages: [],
  tasks: [],
  traces: [],
  activeId: null,
});

// A deliberately small, deterministic UI simulator; this is not model inference.
// Negation/ambiguous input is left for clarification, never interpreted as approval.
function demoIntents(text: string): Kind[] {
  if (/不要|不用|别|取消|不需要|假如|如果/.test(text)) return [];
  const kinds: Kind[] = [];
  if (/报修|异响|故障|报警/.test(text)) kinds.push('repair');
  if (/进度|查.*工单|工单.*状态/.test(text)) kinds.push('progress');
  if (/保养/.test(text)) kinds.push('maintenance');
  return kinds;
}

export function AgentDesk({
  company,
  devices,
  tickets,
  onCreateRepair,
  onViewTicket,
}: Props) {
  const [session, setSession] = useState<Session>(initialSession);
  const [input, setInput] = useState('');
  const logRef = useRef<HTMLDivElement>(null);
  const committed = useRef(new Set<string>());
  const scopeReady = company !== 'all';
  const active = session.tasks.find((t) => t.id === session.activeId);
  const currentDevice = devices.find((d) => d.id === active?.deviceId);
  const pending = session.tasks.filter(
    (t) => !['done', 'manual'].includes(t.stage),
  );
  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [session.messages.length]);

  function send(text: string) {
    const request = text.trim();
    if (!request || !scopeReady) return;
    const kinds = demoIntents(request);
    const newTasks: Task[] = kinds.map((kind) => ({
      id: id(),
      kind,
      stage: kind === 'progress' ? 'done' : 'device',
      request,
      deviceId: '',
      symptom: '',
      result: '',
    }));
    const messages = [message(request, 'user')];
    const traces: Trace[] = [];
    if (newTasks.length === 0) {
      const task: Task = {
        id: id(),
        kind: 'manual',
        stage: 'manual',
        request,
        deviceId: '',
        symptom: '',
        result:
          '当前演示无法可靠确定需求，请由人工核实。没有执行建单或取消操作。',
      };
      newTasks.push(task);
      messages.push(
        message(
          '这条需求需要进一步确认。我已保留原文并标记为待人工接手（本地演示），没有执行业务操作。你也可以体验下方的报修、进度或保养样例。',
        ),
      );
    } else {
      messages.push(
        message(
          `本地演示将这条消息分为 ${newTasks.length} 个任务：${kinds.map((kind) => names[kind]).join('、')}。${kinds.includes('repair') ? '报修先确认设备；独立查询可以先返回结果。' : '接下来按任务逐项处理。'}`,
        ),
      );
      for (const task of newTasks) {
        if (task.kind === 'progress') {
          const ticketReference = request.match(/DEMO-[A-Z0-9-]+/i)?.[0];
          // The fixture timeline is explicitly dated 2026-09-26, not today's live data.
          const results = tickets.filter(
            (t) =>
              t.company === company &&
              (!ticketReference ||
                t.id.toUpperCase() === ticketReference.toUpperCase()) &&
              (!/昨天/.test(request) || t.createdAt.startsWith('09-25')),
          );
          task.result = results.length
            ? `查询到 ${results.length} 条示例记录。`
            : '当前企业范围内没有匹配的示例工单。';
          messages.push(
            message(
              `${task.result}${/昨天/.test(request) ? '“昨天”按示例时间 2026-09-26 解释。' : ''}这是本地数据查询结果，未调用真实服务。`,
              'agent',
              results.map((t) => t.id),
            ),
          );
          traces.push({
            id: id(),
            taskId: task.id,
            title: 'list_company_tickets · 模拟返回',
            input: `企业：${company}；${ticketReference || (/昨天/.test(request) ? '示例日期：09-25' : '当前示例工单')}`,
            output:
              results.map((t) => `${t.id}：${t.status}`).join('\n') ||
              '无匹配记录；不自动创建工单',
          });
        } else {
          messages.push(
            message(
              `${names[task.kind]}已保留。请在下方任务卡片选择并确认设备${task.kind === 'repair' ? '，再补充故障现象' : '，然后查看对应型号的保养周期'}。`,
            ),
          );
        }
      }
    }
    setSession((s) => ({
      messages: [...s.messages, ...messages],
      tasks: [...s.tasks, ...newTasks],
      traces: [...s.traces, ...traces],
      activeId:
        newTasks.find((t) => t.stage === 'device')?.id || newTasks[0].id,
    }));
    setInput('');
  }

  function patchTask(taskId: string, patch: Partial<Task>) {
    setSession((s) => ({
      ...s,
      tasks: s.tasks.map((task) =>
        task.id === taskId ? { ...task, ...patch } : task,
      ),
    }));
  }

  function confirmDevice(task: Task) {
    const device = devices.find(
      (d) => d.id === task.deviceId && d.company === company,
    );
    if (!device || task.stage !== 'device') return;
    const maintenance =
      device.maintenanceDays < 0
        ? `保养已逾期 ${-device.maintenanceDays} 天`
        : `${device.maintenanceDays} 天后到达保养周期`;
    const result =
      task.kind === 'maintenance'
        ? `${device.name}（${device.id}）：${maintenance}。项目：${device.maintenanceItems.join('、')}。未发送提醒或安排派单。`
        : '';
    setSession((s) => ({
      ...s,
      tasks: s.tasks.map((t) =>
        t.id === task.id
          ? {
              ...t,
              stage: task.kind === 'maintenance' ? 'done' : 'details',
              result,
            }
          : t,
      ),
      messages: [
        ...s.messages,
        message(
          `已确认 ${device.company} / ${device.name} / ${device.id}。`,
          'user',
        ),
        message(
          task.kind === 'maintenance'
            ? `示例保养查询结果：${result}`
            : '设备已确认。请在任务卡片补充故障现象、报警代码或发生时间，我会先给出报修信息供你核对。',
        ),
      ],
      traces: [
        ...s.traces,
        {
          id: id(),
          taskId: task.id,
          title:
            task.kind === 'maintenance'
              ? 'query_maintenance · 模拟返回'
              : '设备确认 · 本地校验',
          input: `${company} / ${device.id}`,
          output: result || '设备在当前演示企业内；等待补齐故障；尚未建单',
        },
      ],
    }));
  }

  function review(task: Task) {
    if (!task.symptom.trim() || task.stage !== 'details') return;
    setSession((s) => ({
      ...s,
      tasks: s.tasks.map((t) =>
        t.id === task.id
          ? { ...t, stage: 'review', symptom: t.symptom.trim() }
          : t,
      ),
      messages: [
        ...s.messages,
        message(task.symptom.trim(), 'user'),
        message(
          '报修信息已补齐。请核对企业、设备与故障描述，点击“确认生成演示工单”后才会生成记录。',
        ),
      ],
    }));
  }

  function create(task: Task) {
    const device = devices.find(
      (d) => d.id === task.deviceId && d.company === company,
    );
    if (
      !device ||
      task.stage !== 'review' ||
      !task.symptom.trim() ||
      committed.current.has(task.id)
    )
      return;
    committed.current.add(task.id);
    const ticket = onCreateRepair({
      device,
      symptom: task.symptom.trim(),
      priority: '普通',
    });
    setSession((s) => ({
      ...s,
      tasks: s.tasks.map((t) =>
        t.id === task.id
          ? {
              ...t,
              stage: 'done',
              ticketId: ticket.id,
              result: `已关联演示工单 ${ticket.id}；未发送飞书通知。`,
            }
          : t,
      ),
      messages: [
        ...s.messages,
        message(
          `已关联演示工单 ${ticket.id}，当前状态为${ticket.status}。你可以打开详情，也可以继续查询另一项需求。工单仅保存在当前页面；没有发送飞书通知。`,
          'agent',
          [ticket.id],
        ),
      ],
      traces: [
        ...s.traces,
        {
          id: id(),
          taskId: task.id,
          title: 'create_repair_ticket · 本地演示',
          input: `企业：${company}\n设备：${device.id}\n故障：${task.symptom}`,
          output: `工单：${ticket.id}\n状态：${ticket.status}\n仅在前端内存创建或复用；没有 HTTP / MCP 调用`,
        },
      ],
    }));
  }

  function handoff(task: Task) {
    if (task.stage === 'done' || task.stage === 'manual') return;
    setSession((s) => ({
      ...s,
      tasks: s.tasks.map((t) =>
        t.id === task.id
          ? {
              ...t,
              stage: 'manual',
              result:
                '保留需求、已确认设备与故障信息，等待人工处理。未通知真实人员。',
            }
          : t,
      ),
      messages: [
        ...s.messages,
        message(
          `“${names[task.kind]}”已标记为待人工接手（演示）。已保留原始需求和确认信息，本任务不会继续自动建单；其他任务不受影响。`,
        ),
      ],
      traces: [
        ...s.traces,
        {
          id: id(),
          taskId: task.id,
          title: '人工接手 · 本地标记',
          input: `需求：${task.request}\n设备：${task.deviceId || '未确认'}\n故障：${task.symptom || '未补充'}`,
          output: '暂停该任务；未通知真实售后人员',
        },
      ],
    }));
  }

  return (
    <div className="fy-agent-desk">
      <section className="fy-conversation" aria-label="Agent 售后对话">
        <div className="fy-conversation-heading">
          <span className="fy-agent-avatar">
            <Wind size={23} />
          </span>
          <div>
            <h2>峰云售后 Agent</h2>
            <p>
              <span className="fy-demo-dot" />
              本地流程演示 · 未连接模型
            </p>
          </div>
          <Link to="/chat" className="fy-text-button">
            真实会话入口 <ArrowRight size={14} />
          </Link>
        </div>
        <div className="fy-conversation-context">
          <MessageSquare size={13} />
          <span>模拟飞书需求</span>
          <span>/</span>
          <strong>{scopeReady ? company : '请先选择一家企业'}</strong>
        </div>
        <div
          ref={logRef}
          className="fy-message-log"
          role="log"
          aria-label="对话记录"
          aria-live="polite"
        >
          <div className="fy-agent-welcome">
            <span className="fy-welcome-icon">
              <Bot size={28} />
            </span>
            <h3>描述问题，跟着任务一起处理。</h3>
            <p>
              我会把需求拆成任务，提示缺失信息，
              <br />
              把查询结果和待确认事项放在同一段对话里。
            </p>
            <div className="fy-example-prompts">
              <button
                disabled={!scopeReady}
                onClick={() =>
                  send('机器有异响，需要报修，顺便查一下现有工单进度')
                }
              >
                <ClipboardList size={17} />
                <span>
                  报修，同时查进度<small>体验两个任务独立推进</small>
                </span>
                <ChevronRight size={15} />
              </button>
              <button
                disabled={!scopeReady}
                onClick={() => send('查一下设备什么时候需要保养')}
              >
                <Wrench size={17} />
                <span>
                  设备什么时候保养？<small>确认设备后查看保养周期</small>
                </span>
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
          {session.messages.map((m) => (
            <div className={`fy-message ${m.role}`} key={m.id}>
              <span className="fy-message-avatar">
                {m.role === 'user' ? '客' : <Wind size={17} />}
              </span>
              <div>
                <span className="fy-message-name">
                  {m.role === 'user'
                    ? '客户输入 · 模拟飞书'
                    : '峰云售后 Agent · 演示'}
                </span>
                <div className="fy-message-bubble">{m.text}</div>
                {m.ticketIds?.map((ticketId) => {
                  const ticket = tickets.find((t) => t.id === ticketId);
                  return (
                    ticket && (
                      <button
                        className="fy-result-ticket"
                        key={ticketId}
                        onClick={() => onViewTicket(ticketId)}
                      >
                        <ClipboardList size={16} />
                        <span>
                          <strong>{ticket.title}</strong>
                          <small>
                            {ticket.id} · {ticket.status}
                          </small>
                        </span>
                        <ArrowRight size={15} />
                      </button>
                    )
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {active && !['done', 'manual'].includes(active.stage) && (
          <div className="fy-agent-action" data-testid="agent-action">
            <div className="fy-agent-action-title">
              <CircleHelp size={17} />
              <strong>{stages[active.stage]}</strong>
              <span>
                {active.id} · {names[active.kind]}
              </span>
            </div>
            {active.stage === 'device' && (
              <>
                <p>请选择本次需求对应的具体设备。候选仅来自当前演示企业。</p>
                <div className="fy-action-fields">
                  <select
                    aria-label="Agent 设备选择"
                    value={active.deviceId}
                    onChange={(e) =>
                      patchTask(active.id, { deviceId: e.target.value })
                    }
                  >
                    <option value="">选择设备序列号</option>
                    {devices
                      .filter((d) => d.company === company)
                      .map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} · {d.id}
                        </option>
                      ))}
                  </select>
                  <button
                    className="fy-button primary"
                    disabled={!currentDevice}
                    onClick={() => confirmDevice(active)}
                  >
                    确认设备 <Check size={14} />
                  </button>
                </div>
              </>
            )}
            {active.stage === 'details' && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  review(active);
                }}
              >
                <label htmlFor="agent-symptom">
                  补充 {currentDevice?.name} 的故障现象
                </label>
                <textarea
                  id="agent-symptom"
                  aria-label="Agent 故障补充"
                  value={active.symptom}
                  onChange={(e) =>
                    patchTask(active.id, { symptom: e.target.value })
                  }
                  maxLength={1000}
                  rows={2}
                  placeholder="例如：今天上午开始出现间歇性异响，没有报警代码。"
                  required
                />
                <button
                  className="fy-button primary"
                  disabled={!active.symptom.trim()}
                >
                  生成报修确认信息 <ArrowRight size={14} />
                </button>
              </form>
            )}
            {active.stage === 'review' && (
              <>
                <dl className="fy-agent-review">
                  <div>
                    <dt>企业</dt>
                    <dd>{company}</dd>
                  </div>
                  <div>
                    <dt>设备</dt>
                    <dd>
                      {currentDevice?.name} · {active.deviceId}
                    </dd>
                  </div>
                  <div>
                    <dt>故障</dt>
                    <dd>{active.symptom}</dd>
                  </div>
                </dl>
                <div className="fy-action-buttons">
                  <button
                    className="fy-button"
                    onClick={() => patchTask(active.id, { stage: 'details' })}
                  >
                    修改信息
                  </button>
                  <button
                    className="fy-button primary"
                    onClick={() => create(active)}
                  >
                    确认生成演示工单 <Check size={14} />
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        <form
          className="fy-agent-composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <textarea
            aria-label="发送给售后 Agent 的需求"
            placeholder={
              scopeReady
                ? '描述新的需求，例如：帮我查一下工单进度…'
                : '请先在上方选择一家企业，再开始对话'
            }
            value={input}
            disabled={!scopeReady}
            maxLength={1000}
            rows={2}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === 'Enter' &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                send(input);
              }
            }}
          />
          <div>
            <span>
              <CornerDownLeft size={12} />
              发送 · Shift + Enter 换行
            </span>
            <button
              type="submit"
              aria-label="发送需求"
              disabled={!scopeReady || !input.trim()}
            >
              <Send size={16} />
            </button>
          </div>
          <p>仅按本地关键词演示流程；真实模型和飞书执行请使用真实会话入口。</p>
        </form>
      </section>

      <aside className="fy-agent-context" aria-label="Agent 当前任务">
        <section className="fy-task-panel">
          <div className="fy-task-heading">
            <h2>当前任务</h2>
            <span>
              {session.tasks.length} 项 · {pending.length} 项待确认
            </span>
          </div>
          {!session.tasks.length ? (
            <div className="fy-task-empty">
              <ClipboardList size={28} />
              <strong>等待第一条需求</strong>
              <p>报修、进度查询和保养会分别保留自己的设备与处理状态。</p>
              <ol>
                <li>
                  <span>01</span>接收需求，拆分任务
                </li>
                <li>
                  <span>02</span>确认设备，补齐信息
                </li>
                <li>
                  <span>03</span>查看结果，跟进处理
                </li>
              </ol>
            </div>
          ) : (
            <div className="fy-task-list">
              {session.tasks.map((task) => (
                <button
                  key={task.id}
                  className={active?.id === task.id ? 'active' : ''}
                  onClick={() =>
                    setSession((s) => ({ ...s, activeId: task.id }))
                  }
                >
                  <span className={`fy-task-status ${task.stage}`}>
                    {task.stage === 'done' ? (
                      <Check size={14} />
                    ) : task.stage === 'manual' ? (
                      <Hand size={14} />
                    ) : (
                      <CircleHelp size={14} />
                    )}
                  </span>
                  <span>
                    <strong>{names[task.kind]}</strong>
                    <small>
                      {task.id} · {stages[task.stage]}
                    </small>
                  </span>
                  <ChevronRight size={14} />
                </button>
              ))}
            </div>
          )}
          {active && (
            <div className="fy-active-task">
              <span className="fy-eyebrow">{active.id}</span>
              <h3>
                {names[active.kind]}
                <span>{stages[active.stage]}</span>
              </h3>
              <dl>
                <div>
                  <dt>当前企业</dt>
                  <dd>{company}</dd>
                </div>
                <div>
                  <dt>关联设备</dt>
                  <dd>
                    {active.deviceId ||
                      (active.kind === 'progress' ? '按企业查询' : '尚未确认')}
                  </dd>
                </div>
                <div>
                  <dt>原始需求</dt>
                  <dd>{active.request}</dd>
                </div>
              </dl>
              {active.result && (
                <p className="fy-task-result">{active.result}</p>
              )}
              {active.kind === 'repair' && (
                <ol className="fy-task-steps">
                  {['确认设备', '补充故障', '确认建单'].map((step, i) => {
                    const index = [
                      'device',
                      'details',
                      'review',
                      'done',
                    ].indexOf(active.stage);
                    return (
                      <li
                        key={step}
                        className={
                          index > i ? 'complete' : index === i ? 'current' : ''
                        }
                      >
                        <span>{index > i ? <Check size={12} /> : i + 1}</span>
                        {step}
                      </li>
                    );
                  })}
                </ol>
              )}
              {!['done', 'manual'].includes(active.stage) && (
                <button className="fy-handoff" onClick={() => handoff(active)}>
                  <Hand size={14} />
                  转人工接手（演示）
                </button>
              )}
              {active.stage === 'manual' && (
                <div className="fy-handoff-summary">
                  <strong>交接摘要</strong>
                  <p>需求：{active.request}</p>
                  <p>设备：{active.deviceId || '待核实'}</p>
                  <p>故障：{active.symptom || '待补充'}</p>
                  <small>仅保留本地交接标记，未通知真实人员。</small>
                </div>
              )}
            </div>
          )}
        </section>
        <section className="fy-agent-evidence">
          <div className="fy-task-heading">
            <h2>执行记录</h2>
            <span>可核对的动作与结果</span>
          </div>
          {!active || !session.traces.some((t) => t.taskId === active.id) ? (
            <p className="fy-evidence-empty">
              {active?.stage === 'device'
                ? '正在等待设备确认，尚未调用业务工具。'
                : '选择任务后查看它的处理记录。'}
            </p>
          ) : (
            session.traces
              .filter((t) => t.taskId === active.id)
              .map((trace) => (
                <details key={trace.id}>
                  <summary>
                    <span>
                      <Check size={13} />
                      {trace.title}
                    </span>
                    <ChevronRight size={13} />
                  </summary>
                  <div>
                    <strong>输入</strong>
                    <p>{trace.input}</p>
                    <strong>结果</strong>
                    <p>{trace.output}</p>
                  </div>
                </details>
              ))
          )}
          <div className="fy-evidence-foot">
            <ShieldCheck size={14} />
            <span>记录显示外部动作与结果，不展示模型内部思考。</span>
          </div>
        </section>
        <p className="fy-agent-scope-note">
          示例数据时间：2026-09-26。切换企业将开始新的演示会话；切换业务页会保留当前会话。刷新后重置。
        </p>
      </aside>
    </div>
  );
}
