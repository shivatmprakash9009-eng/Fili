"use client";

import AuthGate from "@/components/AuthGate";
import Dashboard from "../dashboard";

export default function DashboardPage() {
  return (
    <AuthGate>
      {(session) => <Dashboard userName={session.name} userEmail={session.email} onSignOut={session.signOut} />}
    </AuthGate>
  );
}
