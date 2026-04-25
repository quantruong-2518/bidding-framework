'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Briefcase,
  PlusCircle,
  ShieldCheck,
} from 'lucide-react';
import { cn } from '@/lib/utils/cn';
import { useAuthStore } from '@/lib/auth/store';

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const ITEMS: NavItem[] = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/bids', label: 'Bids', icon: Briefcase },
  { href: '/bids/new', label: 'New bid', icon: PlusCircle },
  { href: '/audit', label: 'Audit', icon: ShieldCheck, adminOnly: true },
];

export function Sidebar(): React.ReactElement {
  const pathname = usePathname();
  const roles = useAuthStore((s) => s.user?.roles ?? []);
  const isAdmin = roles.includes('admin');
  const visible = ITEMS.filter((i) => !i.adminOnly || isAdmin);

  return (
    <aside className="hidden w-56 shrink-0 border-r border-border bg-card lg:flex lg:flex-col">
      <div className="flex h-14 items-center border-b border-border px-4">
        <Link href="/dashboard" className="flex items-center gap-2 font-semibold">
          <span className="inline-block h-2 w-2 rounded-full bg-primary" />
          AI Bidding
        </Link>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {visible.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                active
                  ? 'bg-primary/10 font-medium text-primary'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
