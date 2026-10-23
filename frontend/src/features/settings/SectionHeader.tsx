import type { ReactNode } from 'react';

export function SectionHeader({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        <p className="muted">{description}</p>
      </div>
      {action}
    </div>
  );
}
