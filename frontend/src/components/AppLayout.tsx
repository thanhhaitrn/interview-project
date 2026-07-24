import { Outlet } from "react-router-dom";
import { NavBar } from "./NavBar";

export function AppLayout() {
  return (
    <div className="min-h-screen px-4 pb-20">
      <NavBar />
      <main className="mx-auto mt-10 max-w-6xl">
        <Outlet />
      </main>
    </div>
  );
}
