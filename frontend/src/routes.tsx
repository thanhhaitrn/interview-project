import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { Home } from "./pages/Home";
import { ResumeList } from "./pages/ResumeList";
import { ResumeEdit } from "./pages/ResumeEdit";
import { Profiles } from "./pages/Profiles";
import { ProfileNew } from "./pages/ProfileNew";
import { Practice } from "./pages/Practice";
import { ReportPage } from "./pages/ReportPage";
import { MockSetup } from "./pages/MockSetup";
import { MockLive } from "./pages/MockLive";
import { MockHistory } from "./pages/MockHistory";
import { MockReview } from "./pages/MockReview";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: "resume", element: <ResumeList /> },
      { path: "resume/:id/edit", element: <ResumeEdit /> },
      { path: "profiles", element: <Profiles /> },
      { path: "profiles/new", element: <ProfileNew /> },
      { path: "practice/:profileId", element: <Practice /> },
      { path: "practice/:profileId/report", element: <ReportPage /> },
      { path: "mock", element: <MockSetup /> },
      { path: "mock/live", element: <MockLive /> },
      { path: "reviews", element: <MockHistory /> },
      { path: "mock/history/:profileId", element: <MockHistory /> },
      { path: "mock/review/:profileId/:runId", element: <MockReview /> },
    ],
  },
]);
