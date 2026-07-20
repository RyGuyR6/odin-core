import { PageHeader } from "@/components/page-header";
import { RuntimeDashboard } from "@/components/dashboard/runtime-dashboard";

export default function DashboardPage() {
  return <><PageHeader eyebrow="OW-004 · Runtime dashboard" title="Odin Control Center" description="Monitor system health, agents, tasks, repositories, and runtime activity." /><RuntimeDashboard /></>;
}
