import {
  MessageCircle,
  Clock4,
  Bot,
  Puzzle,
  BarChart3,
  Wallet,
  Settings,
  LayoutDashboard,
} from 'lucide-react';

interface NavItem {
  path: string;
  icon: typeof MessageCircle;
  label: string;
  requiresBilling?: boolean;
  hideOnMobile?: boolean;
}

export const baseNavItems: NavItem[] = [
  { path: '/service', icon: LayoutDashboard, label: '售后' },
  { path: '/chat', icon: MessageCircle, label: '会话' },
  { path: '/agent-profiles', icon: Bot, label: '智能体', hideOnMobile: true },
  { path: '/capabilities', icon: Puzzle, label: '能力库', hideOnMobile: true },
  { path: '/tasks', icon: Clock4, label: '定时任务' },
  { path: '/usage', icon: BarChart3, label: '用量', hideOnMobile: true },
  {
    path: '/billing',
    icon: Wallet,
    label: '账单',
    requiresBilling: true,
    hideOnMobile: true,
  },
  { path: '/settings', icon: Settings, label: '设置' },
];

export function filterNavItems(billingEnabled: boolean) {
  return baseNavItems.filter((item) => !item.requiresBilling || billingEnabled);
}
