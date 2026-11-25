"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { ReactNode } from "react";

interface NavItem {
  label: string;
  href: string;
  icon: string;
  section?: string;
}

const navigation: NavItem[] = [
  { section: "WORKSPACE", label: "Overview", href: "/", icon: "▦" },
  { section: "WORKSPACE", label: "All invoices", href: "/invoices", icon: "▤" },
  { section: "WORKSPACE", label: "Live processing", href: "/processing", icon: "⌁" },
  { section: "WORKSPACE", label: "Exception centre", href: "/exceptions", icon: "⚑" },
  { section: "WORKSPACE", label: "Approvals", href: "/approvals", icon: "✓" },
  { section: "CONFIGURATION", label: "Suppliers", href: "/suppliers", icon: "▣" },
  { section: "CONFIGURATION", label: "Settings", href: "/settings", icon: "⚙" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark">I</div>
          <div>
            <strong>Invoice Intelligence</strong>
            <span>AP WORKSPACE</span>
          </div>
        </div>

        {navigation.map((item, idx) => {
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          const showSectionLabel = idx === 0 || navigation[idx - 1].section !== item.section;

          return (
            <React.Fragment key={item.href}>
              {showSectionLabel && (
                <div className="navLabel">{item.section}</div>
              )}
              <Link
                href={item.href}
                className={`navItem ${isActive ? "active" : ""}`}
              >
                {item.icon} <span>{item.label}</span>
              </Link>
            </React.Fragment>
          );
        })}

        <div className="sidebarFoot">
          Development workspace
          <br />
          <span>Local environment</span>
        </div>
      </aside>

      <section className="content">{children}</section>
    </main>
  );
}