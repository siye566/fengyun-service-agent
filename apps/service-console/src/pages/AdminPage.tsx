import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  ExternalLink,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Users,
  Wind,
  Wrench,
} from "lucide-react";
import "./admin.css";

type Session = { authenticated: boolean; configured: boolean; csrf?: string };
type Feishu = {
  app_id: string;
  has_secret: boolean;
  enabled: boolean;
  runtime_state: string;
  last_error: string;
  last_received_at: string | null;
};
type Overview = {
  stats: Record<string, number>;
  companies: string[];
  feishu: Feishu;
  mode: string;
};
type Conversation = {
  id: string;
  channel: string;
  customer: string;
  company: string;
  updated_at: string;
  last_message: string;
};
type Message = {
  id: number;
  utterance: string;
  reply_text: string;
  delivery?: string;
  delivery_error?: string;
  created_at: string;
  company_name?: string;
};
type Detail = {
  id: string;
  channel: string;
  customer: string;
  company: string;
  state: {
    stage: string;
    pending: { device_serial: string; symptom: string } | null;
  };
  messages: Message[];
  older_cursor: number | null;
};
type Ticket = {
  ticket_no: string;
  company_name: string;
  device_serial: string;
  symptom: string;
  status_text: string;
  created_at: string;
};
type Device = {
  serial_no: string;
  company_name: string;
  model: string;
  last_maintenance_date: string;
  maintenance_interval_days: number;
};
type Tab = "conversations" | "tickets" | "devices" | "feishu";
type Page<T> = { items: T[]; has_more: boolean };

const stageNames: Record<string, string> = {
  idle: "尚无报修任务",
  awaiting_details: "等待客户补充",
  awaiting_confirmation: "等待客户确认",
  confirming: "正在提交",
  completed: "报修已受理",
  cancelled: "客户已取消",
};
function time(value?: string | null) {
  return value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false })
    : "暂无记录";
}
function channelStatus(config?: Feishu) {
  if (!config?.app_id) return "尚未配置";
  if (!config.enabled) return "已停用";
  if (config.runtime_state === "error") return "连接异常";
  if (config.last_received_at) return "已收到消息";
  return config.runtime_state === "starting" ? "正在启动" : "待收发验证";
}
async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/admin/${path}`, {
    credentials: "same-origin",
    ...init,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "输入未通过校验，请检查填写内容",
    );
  return data;
}

export function AdminPage() {
  const [session, setSession] = useState<Session>();
  const [password, setPassword] = useState("");
  const [tab, setTab] = useState<Tab>("conversations");
  const [overview, setOverview] = useState<Overview>();
  const [conversations, setConversations] = useState<Page<Conversation>>({
    items: [],
    has_more: false,
  });
  const [channel, setChannel] = useState("all");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Detail>();
  const [company, setCompany] = useState("");
  const [tickets, setTickets] = useState<Page<Ticket>>({
    items: [],
    has_more: false,
  });
  const [devices, setDevices] = useState<Page<Device>>({
    items: [],
    has_more: false,
  });
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadedAt, setLoadedAt] = useState("");

  useEffect(() => {
    json<Session>("session")
      .then(setSession)
      .catch((e) => setError(e.message));
  }, []);
  const refresh = useCallback(async () => {
    const latest = await json<Overview>("overview");
    setOverview(latest);
    if (tab === "conversations")
      setConversations(
        await json(
          `conversations?channel=${channel}&q=${encodeURIComponent(search)}&offset=${offset}`,
        ),
      );
    if (tab === "tickets") setTickets(await json(`tickets?offset=${offset}`));
    if (tab === "devices") setDevices(await json(`devices?offset=${offset}`));
    setLoadedAt(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
  }, [tab, channel, search, offset]);
  useEffect(() => {
    if (!session?.authenticated) return;
    refresh().catch((e) => setError(e.message));
    const timer = setInterval(() => {
      refresh().catch((e) => setError(e.message));
    }, 15000);
    return () => clearInterval(timer);
  }, [session?.authenticated, refresh]);
  useEffect(() => {
    if (!selected || !session?.authenticated || tab !== "conversations") return;
    let active = true;
    const load = () =>
      json<Detail>(`conversations/${selected}`)
        .then((data) => {
          if (active) {
            setDetail(data);
            setCompany(data.company);
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    load();
    const timer = setInterval(load, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selected, tab, session?.authenticated]);
  useEffect(() => {
    if (tab === "feishu" && overview) {
      setAppId(overview.feishu.app_id);
      setEnabled(overview.feishu.enabled);
      setAppSecret("");
    }
  }, [tab]);

  async function mutate<T>(path: string, body: object): Promise<T> {
    return json<T>(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": session?.csrf ?? "",
      },
      body: JSON.stringify(body),
    });
  }
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }
  function switchTab(next: Tab) {
    setTab(next);
    setOffset(0);
    setError("");
    setNotice("");
  }
  function selectConversation(id: string) {
    setSelected(id);
    setDetail(undefined);
    setNotice("");
  }
  async function older() {
    if (!detail?.older_cursor) return;
    const more = await json<Detail>(
      `conversations/${detail.id}?before=${detail.older_cursor}`,
    );
    setDetail({
      ...detail,
      older_cursor: more.older_cursor,
      messages: [...more.messages, ...detail.messages],
    });
  }

  if (!session?.authenticated)
    return (
      <main className="ops-login">
        <section className="ops-intro">
          <div className="ops-brand">
            <Wind size={28} />
            <span>
              空压机售后<span>SERVICE OPERATIONS</span>
            </span>
          </div>
          <div>
            <span className="ops-eyebrow">售后服务管理中心</span>
            <h1>
              客户在飞书报修，
              <br />
              售后在这里跟进。
            </h1>
            <p>查看客户会话、核对报修进度，统一管理飞书接入和企业身份。</p>
            <div className="ops-login-flow">
              <span>
                <MessageSquare />
                飞书客户消息
              </span>
              <ArrowRight />
              <span>
                <ShieldCheck />
                业务校验
              </span>
              <ArrowRight />
              <span>
                <ClipboardList />
                售后工单
              </span>
            </div>
          </div>
          <small>会话与工单保存至 PostgreSQL · 管理入口需要登录</small>
        </section>
        <section className="ops-login-panel">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                const next = await mutate<Session>("login", { password });
                setPassword("");
                setSession(next);
              });
            }}
          >
            <div className="ops-login-icon">
              <ShieldCheck size={26} />
            </div>
            <span className="ops-eyebrow">ADMIN CONSOLE</span>
            <h2>登录管理员工作台</h2>
            <p>管理员可以查看各企业的售后会话和工单。</p>
            <label>
              管理员密码
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                maxLength={256}
              />
            </label>
            {error && (
              <div role="alert" className="ops-error">
                {error}
              </div>
            )}
            {session && !session.configured && (
              <div className="ops-note">
                尚未配置管理员密码，请在服务器运行更新后的部署脚本。
              </div>
            )}
            <button
              className="ops-primary"
              disabled={busy || !session || !session.configured}
            >
              {busy ? "正在验证…" : "进入管理工作台"}
              <ArrowRight size={17} />
            </button>
            <small>密码由服务器部署脚本生成，与服务器 SSH 密码分别管理。</small>
            <a className="ops-experience" href="/experience">
              打开客户报修体验页 <ExternalLink size={14} />
            </a>
          </form>
        </section>
      </main>
    );

  const config = overview?.feishu;
  const nav = [
    { id: "conversations" as const, label: "客户会话", icon: MessageSquare },
    { id: "tickets" as const, label: "全部工单", icon: ClipboardList },
    { id: "devices" as const, label: "设备台账", icon: Wrench },
    { id: "feishu" as const, label: "飞书接入", icon: Settings2 },
  ];
  return (
    <div className="ops-app">
      <aside className="ops-sidebar">
        <a className="ops-brand" href="/">
          <Wind size={26} />
          <span>
            售后服务台<span>SERVICE OPERATIONS</span>
          </span>
        </a>
        <div className="ops-nav-label">工作空间</div>
        <nav>
          {nav.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
              onClick={() => switchTab(id)}
            >
              <Icon size={19} />
              {label}
              {id === "conversations" && !!overview?.stats.unbound && (
                <b>{overview.stats.unbound}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="ops-sidebar-bottom">
          <span className="ops-status-dot" />
          PostgreSQL 持久化<p>业务规则模式 · 客户确认后建单</p>
          <a href="/experience" target="_blank" rel="noreferrer">
            客户体验入口
            <ExternalLink size={14} />
          </a>
          <button
            onClick={() =>
              run(async () => {
                await mutate("logout", {});
                setSession({ authenticated: false, configured: true });
                setOverview(undefined);
                setDetail(undefined);
              })
            }
          >
            <LogOut size={16} />
            退出管理员
          </button>
        </div>
      </aside>
      <main className="ops-main">
        <header className="ops-header">
          <div>
            <span className="ops-eyebrow">
              售后运营 / {nav.find((n) => n.id === tab)?.label}
            </span>
            <h1>{nav.find((n) => n.id === tab)?.label}</h1>
            <p>
              {tab === "conversations"
                ? "集中查看飞书客户和网页体验会话，跟进每一条售后需求。"
                : tab === "feishu"
                  ? "配置企业自建应用，客户通过飞书机器人私聊发起报修。"
                  : tab === "tickets"
                    ? "查看各企业已确认提交的售后工单。"
                    : "查看企业归属与设备信息，核对客户可报修的设备。"}
            </p>
          </div>
          <div className="ops-header-actions">
            <span className="ops-channel-state">
              <span
                className={
                  config?.last_received_at ? "ops-status-dot" : "ops-muted-dot"
                }
              />
              飞书 · {channelStatus(config)}
            </span>
            <button
              className="ops-button"
              disabled={busy}
              onClick={() => run(refresh)}
            >
              <RefreshCw size={15} />
              刷新
            </button>
            <button
              className="ops-mobile-logout"
              aria-label="退出管理员"
              onClick={() =>
                run(async () => {
                  await mutate("logout", {});
                  setSession({ authenticated: false, configured: true });
                  setOverview(undefined);
                  setDetail(undefined);
                })
              }
            >
              <LogOut size={15} />
            </button>
          </div>
        </header>
        {error && (
          <div role="alert" className="ops-error">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="ops-success">
            <Check size={16} />
            {notice}
          </div>
        )}
        <section className="ops-stats" aria-label="业务概览">
          {[
            {
              label: "飞书客户会话",
              value: overview?.stats.feishu_conversations ?? 0,
              icon: MessageSquare,
            },
            {
              label: "等待身份绑定",
              value: overview?.stats.unbound ?? 0,
              icon: Users,
            },
            {
              label: "待派单工单",
              value: overview?.stats.pending_tickets ?? 0,
              icon: ClipboardList,
            },
            {
              label: "全部工单",
              value: overview?.stats.tickets ?? 0,
              icon: LayoutDashboard,
            },
          ].map(({ label, value, icon: Icon }) => (
            <article key={label}>
              <div>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
              <Icon size={20} />
            </article>
          ))}
        </section>

        {tab === "conversations" && (
          <>
            <section className="ops-panel ops-conversation-panel">
              <div className="ops-panel-heading">
                <div>
                  <h2>会话中心</h2>
                  <p>客户消息与系统回复按会话保存</p>
                </div>
                <span className="ops-subtle">
                  15 秒更新 · {loadedAt || "正在加载"}
                </span>
              </div>
              <div className="ops-conversation-grid">
                <div className="ops-conversation-list">
                  <div className="ops-filters">
                    <div className="ops-segments">
                      {[
                        ["all", "全部"],
                        ["feishu", "飞书"],
                        ["web", "网页体验"],
                      ].map(([id, name]) => (
                        <button
                          key={id}
                          className={channel === id ? "active" : ""}
                          onClick={() => {
                            setChannel(id);
                            setOffset(0);
                          }}
                        >
                          {name}
                        </button>
                      ))}
                    </div>
                    <form
                      className="ops-search"
                      onSubmit={(e) => {
                        e.preventDefault();
                        setSearch(query);
                        setOffset(0);
                      }}
                    >
                      <Search size={16} />
                      <input
                        aria-label="搜索客户会话"
                        placeholder="搜索客户、企业或消息"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                      <button aria-label="提交搜索">
                        <ArrowRight size={16} />
                      </button>
                    </form>
                  </div>
                  <div className="ops-list-scroll">
                    {conversations.items.map((item) => (
                      <button
                        key={item.id}
                        className={`ops-conversation-item ${selected === item.id ? "selected" : ""}`}
                        onClick={() => selectConversation(item.id)}
                      >
                        <div className={`ops-avatar ${item.channel}`}>
                          <MessageSquare size={20} />
                        </div>
                        <div className="ops-conversation-summary">
                          <div>
                            <strong>{item.company || "待绑定客户"}</strong>
                            <span>
                              {item.channel === "feishu" ? "飞书" : "网页"}
                            </span>
                          </div>
                          <p>{item.last_message || "尚未发送消息"}</p>
                          <small>{time(item.updated_at)}</small>
                        </div>
                      </button>
                    ))}
                    {!conversations.items.length && (
                      <div className="ops-empty">
                        <MessageSquare size={30} />
                        <h3>暂无匹配的会话</h3>
                        <p>完成飞书接入后，让客户给机器人发送一条私聊消息。</p>
                        <button
                          className="ops-button"
                          onClick={() => switchTab("feishu")}
                        >
                          配置飞书接入
                          <ArrowRight size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                  <Pager
                    offset={offset}
                    hasMore={conversations.has_more}
                    onChange={setOffset}
                  />
                </div>
                <div className="ops-conversation-detail">
                  {detail ? (
                    <>
                      <div className="ops-thread-header">
                        <div>
                          <h3>{detail.company || "待绑定客户"}</h3>
                          <p>
                            {detail.channel === "feishu"
                              ? "飞书私聊"
                              : "网页体验"}{" "}
                            · {detail.customer}
                          </p>
                        </div>
                        <span className="ops-tag">
                          {stageNames[detail.state.stage] ?? detail.state.stage}
                        </span>
                      </div>
                      {detail.channel === "feishu" && (
                        <form
                          className="ops-binding"
                          onSubmit={(e) => {
                            e.preventDefault();
                            run(async () => {
                              await mutate("bindings", {
                                conversation_id: detail.id.slice(7),
                                company_name: company,
                              });
                              setDetail(
                                await json(`conversations/${detail.id}`),
                              );
                              await refresh();
                              setNotice(
                                company
                                  ? "企业身份已绑定，客户可继续在飞书报修。"
                                  : "已解除企业绑定。",
                              );
                            });
                          }}
                        >
                          <label>
                            所属企业
                            <select
                              aria-label="客户所属企业"
                              value={company}
                              onChange={(e) => setCompany(e.target.value)}
                            >
                              <option value="">
                                未绑定 · 拒绝访问业务数据
                              </option>
                              {overview?.companies.map((name) => (
                                <option key={name}>{name}</option>
                              ))}
                            </select>
                          </label>
                          <button className="ops-button" disabled={busy}>
                            保存身份绑定
                          </button>
                        </form>
                      )}
                      {detail.state.pending && (
                        <div className="ops-pending">
                          <ClipboardList size={18} />
                          <div>
                            <strong>{stageNames[detail.state.stage]}</strong>
                            <p>
                              {detail.state.pending.device_serial ||
                                "设备待补充"}{" "}
                              · {detail.state.pending.symptom || "故障待补充"}
                            </p>
                          </div>
                        </div>
                      )}
                      <div
                        className="ops-thread"
                        role="log"
                        aria-label="客户会话记录"
                      >
                        {detail.older_cursor && (
                          <button
                            className="ops-button ops-older"
                            onClick={() => run(older)}
                          >
                            加载更早消息
                          </button>
                        )}
                        {!detail.messages.length && (
                          <p className="ops-subtle">这个会话还没有消息。</p>
                        )}
                        {detail.messages.map((message) => (
                          <div className="ops-turn" key={message.id}>
                            <div className="ops-message customer">
                              <span>客户 · {time(message.created_at)}</span>
                              <p>{message.utterance}</p>
                            </div>
                            <div className="ops-message assistant">
                              <span>
                                售后助手{" "}
                                {message.delivery && (
                                  <b
                                    className={
                                      message.delivery === "failed"
                                        ? "ops-failed"
                                        : ""
                                    }
                                  >
                                    {message.delivery === "sent"
                                      ? "已发送至飞书"
                                      : message.delivery === "failed"
                                        ? "发送失败"
                                        : "待发送"}
                                  </b>
                                )}
                              </span>
                              <p>{message.reply_text}</p>
                              {message.delivery_error && (
                                <small className="ops-failed">
                                  {message.delivery_error}
                                </small>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                      <div className="ops-readonly">
                        <ShieldCheck size={14} />
                        管理台用于查看与身份管理，报修由客户在飞书明确确认。
                      </div>
                    </>
                  ) : (
                    <div className="ops-empty ops-select-empty">
                      <BookOpen size={36} />
                      <h3>{selected ? "正在读取会话…" : "选择一个客户会话"}</h3>
                      <p>查看消息记录、当前报修任务和回复发送状态。</p>
                      <span>飞书客户的企业身份由管理员绑定</span>
                    </div>
                  )}
                </div>
              </div>
            </section>
            {!!overview?.stats.failed_replies && (
              <div className="ops-note">
                有 {overview.stats.failed_replies}{" "}
                条回复发送失败。请查看对应会话，并检查飞书权限及网络；系统最多自动尝试
                5 次。
              </div>
            )}
          </>
        )}

        {tab === "tickets" && (
          <section className="ops-panel">
            <div className="ops-panel-heading">
              <div>
                <h2>全部企业工单</h2>
                <p>仅显示客户已确认并保存的工单</p>
              </div>
            </div>
            <div className="ops-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>工单号</th>
                    <th>所属企业</th>
                    <th>设备 / 故障</th>
                    <th>处理状态</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {tickets.items.map((item) => (
                    <tr key={item.ticket_no}>
                      <td>
                        <strong>{item.ticket_no}</strong>
                      </td>
                      <td>{item.company_name}</td>
                      <td>
                        {item.device_serial}
                        <small>{item.symptom}</small>
                      </td>
                      <td>
                        <span className="ops-tag">{item.status_text}</span>
                      </td>
                      <td>{time(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!tickets.items.length && (
              <div className="ops-empty">
                <ClipboardList size={30} />
                <h3>还没有已提交工单</h3>
                <p>
                  客户核对设备和故障，并回复“确认报修”后，工单会显示在这里。
                </p>
              </div>
            )}
            <Pager
              offset={offset}
              hasMore={tickets.has_more}
              onChange={setOffset}
            />
          </section>
        )}
        {tab === "devices" && (
          <section className="ops-panel">
            <div className="ops-panel-heading">
              <div>
                <h2>设备台账</h2>
                <p>公开项目初始台账使用示例企业和 DEMO 设备</p>
              </div>
            </div>
            <div className="ops-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>设备序列号</th>
                    <th>所属企业</th>
                    <th>型号</th>
                    <th>上次保养</th>
                    <th>保养周期</th>
                  </tr>
                </thead>
                <tbody>
                  {devices.items.map((item) => (
                    <tr key={item.serial_no}>
                      <td>
                        <strong>{item.serial_no}</strong>
                      </td>
                      <td>{item.company_name}</td>
                      <td>{item.model}</td>
                      <td>{item.last_maintenance_date}</td>
                      <td>{item.maintenance_interval_days} 天</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              offset={offset}
              hasMore={devices.has_more}
              onChange={setOffset}
            />
          </section>
        )}

        {tab === "feishu" && (
          <div className="ops-settings-grid">
            <section className="ops-panel">
              <div className="ops-panel-heading">
                <div>
                  <h2>飞书机器人</h2>
                  <p>企业自建应用 · 官方 SDK 长连接</p>
                </div>
                <span className="ops-tag">{channelStatus(config)}</span>
              </div>
              <form
                className="ops-settings-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  run(async () => {
                    await mutate("feishu", {
                      app_id: appId.trim(),
                      app_secret: appSecret,
                      enabled,
                    });
                    setAppSecret("");
                    await refresh();
                    setNotice(
                      "飞书配置已保存。启用后约 5 秒启动接收进程，请继续验证实际收发。",
                    );
                  });
                }}
              >
                <label>
                  App ID
                  <input
                    placeholder="cli_…"
                    autoComplete="off"
                    value={appId}
                    onChange={(e) => setAppId(e.target.value)}
                    required
                    pattern="cli_[a-zA-Z0-9]{3,100}"
                  />
                </label>
                <label>
                  App Secret
                  <input
                    type="password"
                    placeholder={
                      config?.has_secret
                        ? "已保存，留空保留原密钥"
                        : "填写应用密钥"
                    }
                    autoComplete="new-password"
                    value={appSecret}
                    onChange={(e) => setAppSecret(e.target.value)}
                    maxLength={256}
                  />
                </label>
                <p className="ops-subtle">
                  密钥加密保存在服务器数据库，接口不返回密钥原文。
                </p>
                <label className="ops-checkbox">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) => setEnabled(e.target.checked)}
                  />
                  启用飞书长连接接收消息
                </label>
                <div className="ops-form-buttons">
                  <button className="ops-primary" disabled={busy}>
                    保存配置
                    <Check size={16} />
                  </button>
                  <button
                    type="button"
                    className="ops-button"
                    disabled={busy || !config?.app_id}
                    onClick={() =>
                      run(async () => {
                        const result = await mutate<{ message: string }>(
                          "feishu/check",
                          {},
                        );
                        setNotice(result.message);
                      })
                    }
                  >
                    验证已保存凭证
                  </button>
                </div>
                <div className="ops-runtime">
                  <div>
                    <span>接收进程</span>
                    <strong>{channelStatus(config)}</strong>
                  </div>
                  <div>
                    <span>最近收到消息</span>
                    <strong>{time(config?.last_received_at)}</strong>
                  </div>
                  {config?.last_error && (
                    <p className="ops-failed">{config.last_error}</p>
                  )}
                </div>
                <div className="ops-note">
                  凭证有效、进程已启动与消息实际送达是不同状态。请通过一次飞书私聊完成验证。
                </div>
              </form>
            </section>
            <aside className="ops-panel ops-guide">
              <span className="ops-eyebrow">接入步骤</span>
              <h2>让客户从飞书发起报修</h2>
              <ol>
                <li>
                  <strong>创建企业自建应用</strong>
                  <p>
                    在飞书开放平台创建应用，添加“机器人”能力，复制 App ID 和 App
                    Secret。
                  </p>
                </li>
                <li>
                  <strong>开启接收与发送权限</strong>
                  <p>
                    开通读取用户发给机器人的单聊消息（im:message.p2p_msg:readonly）及以应用身份发消息（im:message:send_as_bot）。
                  </p>
                </li>
                <li>
                  <strong>保存配置并启用长连接</strong>
                  <p>
                    填写左侧凭证并保存，在飞书“事件与回调”选择长连接，订阅接收消息事件
                    im.message.receive_v1。
                  </p>
                </li>
                <li>
                  <strong>发布应用并设置可用范围</strong>
                  <p>
                    确保测试用户在应用可用范围内。应用变更按企业要求发布、审核或授权。
                  </p>
                </li>
                <li>
                  <strong>接收消息并绑定企业</strong>
                  <p>
                    客户先私聊机器人发送“报修”，管理员在“客户会话”中选择该客户并绑定所属企业。
                  </p>
                </li>
                <li>
                  <strong>验证确认后建单</strong>
                  <p>
                    使用台账中的示例设备，例如绑定示例企业甲后发送“报修
                    DEMO-GR75-0001 机器异响”，核对后回复“确认报修”。
                  </p>
                </li>
              </ol>
              <a
                className="ops-doc-link"
                href="https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/handle-events"
                target="_blank"
                rel="noreferrer"
              >
                飞书官方接入说明
                <ExternalLink size={15} />
              </a>
              <div className="ops-note">
                当前支持机器人私聊文本；群聊、附件和模型生成回复需另行接入。已有聊天历史不会自动导入。
              </div>
            </aside>
          </div>
        )}
        <footer className="ops-footer">
          <span>
            <ShieldCheck size={14} />
            管理员视角 · 全企业会话与工单
          </span>
          <span>业务规则处理 · 客户确认门禁</span>
        </footer>
      </main>
    </div>
  );
}

function Pager({
  offset,
  hasMore,
  onChange,
}: {
  offset: number;
  hasMore: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <div className="ops-pager">
      <span>第 {Math.floor(offset / 50) + 1} 页</span>
      <button
        aria-label="上一页"
        disabled={!offset}
        onClick={() => onChange(Math.max(0, offset - 50))}
      >
        <ChevronLeft size={17} />
      </button>
      <button
        aria-label="下一页"
        disabled={!hasMore}
        onClick={() => onChange(offset + 50)}
      >
        <ChevronRight size={17} />
      </button>
    </div>
  );
}
