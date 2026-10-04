// Isolated UI fixtures. These are never sent to ACS or used as authorization.
export const companies = [
  '示例企业甲',
  '示例企业乙',
  '示例企业丙',
];
export type TicketStatus = '待确认' | '待处理' | '处理中' | '已完成';
export interface Device {
  id: string;
  company: string;
  name: string;
  model: string;
  location: string;
  maintenanceDays: number;
  maintenanceItems: string[];
}
export interface ServiceEvent {
  time: string;
  title: string;
  detail: string;
}
export interface Ticket {
  id: string;
  company: string;
  deviceId: string;
  title: string;
  status: TicketStatus;
  source: '飞书' | '工作台';
  priority: '普通' | '紧急';
  createdAt: string;
  events: ServiceEvent[];
}
export const devices: Device[] = [
  {
    id: 'DEMO-GR75-0001',
    company: companies[0],
    name: '1 号空压机',
    model: 'GR-75',
    location: '后勤动力站',
    maintenanceDays: 5,
    maintenanceItems: [
      '空滤芯检查更换',
      '油滤芯更换',
      '油气分离芯压差检查',
      '皮带张紧与磨损检查',
      '冷却器翅片吹扫',
      '安全阀校验',
    ],
  },
  {
    id: 'DEMO-GR75-0002',
    company: companies[1],
    name: '2 号空压机',
    model: 'GR-75',
    location: 'B 厂 · 空压站',
    maintenanceDays: -17,
    maintenanceItems: [
      '空滤芯检查更换',
      '油滤芯更换',
      '油气分离芯压差检查',
      '皮带张紧与磨损检查',
      '冷却器翅片吹扫',
      '安全阀校验',
    ],
  },
  {
    id: 'DEMO-EP30-0007',
    company: companies[2],
    name: '7 号空压机',
    model: 'EP-30',
    location: '一车间 · 动力房',
    maintenanceDays: 161,
    maintenanceItems: ['空滤芯检查更换', '管路接头检漏'],
  },
];
export function createDemoTickets(): Ticket[] {
  return [
    {
      id: 'DEMO-0926-001',
      company: companies[0],
      deviceId: devices[0].id,
      title: '运行时出现异响，需要协助排查',
      status: '待确认',
      source: '飞书',
      priority: '普通',
      createdAt: '09-26 09:42',
      events: [
        {
          time: '09:42',
          title: '收到报修消息',
          detail: '飞书 · “动力站的机器有异响，帮我看看。”',
        },
        {
          time: '09:42',
          title: '等待设备确认',
          detail: '已找到候选设备 DEMO-GR75-0001，需用户确认后再建单。',
        },
      ],
    },
    {
      id: 'DEMO-0926-002',
      company: companies[1],
      deviceId: devices[1].id,
      title: 'E3 报警，排气温度异常',
      status: '处理中',
      source: '飞书',
      priority: '紧急',
      createdAt: '09-26 09:18',
      events: [
        {
          time: '09:18',
          title: '设备已确认',
          detail: '示例企业乙 · DEMO-GR75-0002',
        },
        {
          time: '09:19',
          title: '报修信息已记录',
          detail: '设备、故障描述和所属企业已关联。',
        },
        {
          time: '09:30',
          title: '售后处理中',
          detail: '等待现场检查结果；本记录为流程演示。',
        },
      ],
    },
    {
      id: 'DEMO-0925-003',
      company: companies[2],
      deviceId: devices[2].id,
      title: '管路接头漏气，运行压力不足',
      status: '已完成',
      source: '工作台',
      priority: '普通',
      createdAt: '09-25 14:06',
      events: [
        {
          time: '09-25 14:06',
          title: '创建报修记录',
          detail: '示例企业丙 · DEMO-EP30-0007',
        },
        {
          time: '09-25 16:20',
          title: '处理完成',
          detail: '示例处理结果：接头检修后恢复正常。',
        },
      ],
    },
    {
      id: 'DEMO-0926-004',
      company: companies[0],
      deviceId: devices[0].id,
      title: '保养前设备运行检查',
      status: '待处理',
      source: '工作台',
      priority: '普通',
      createdAt: '09-26 08:50',
      events: [
        {
          time: '08:50',
          title: '检查需求已登记',
          detail: '设备将在 5 天后到达保养周期，等待人工安排。',
        },
      ],
    },
  ];
}
export const statusTone: Record<TicketStatus, string> = {
  待确认: 'amber',
  待处理: 'blue',
  处理中: 'teal',
  已完成: 'gray',
};
