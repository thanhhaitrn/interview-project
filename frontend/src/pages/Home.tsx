import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui";

export function Home() {
  const navigate = useNavigate();
  return (
    <div className="grid items-center gap-10 md:grid-cols-2">
      <div>
        <p className="text-navy/50">Interview practice, but actually personal.</p>
        <h1 className="mt-3 text-5xl font-extrabold leading-tight tracking-tight">
          AI-powered interview practice, personalized to you.
        </h1>
        <p className="mt-5 max-w-md text-lg text-navy/60">
          Your resume + the job description = questions and answers tailored to
          your dream job — so you can prepare like it's the real interview.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button onClick={() => navigate("/profiles/new")}>
            Create new interview profile
          </Button>
          <Button variant="subtle" onClick={() => navigate("/profiles")}>
            Browse past practice
          </Button>
        </div>
      </div>

      <div className="rounded-4xl bg-navy p-6 text-white shadow-2xl">
        <div className="flex items-center justify-between text-xs text-white/60">
          <span className="rounded-full border border-white/20 px-3 py-1">
            Amazon · DS Intern
          </span>
          <span>Practice session</span>
        </div>
        <p className="mt-4 text-xs uppercase tracking-wide text-white/50">
          Question
        </p>
        <p className="mt-1 text-sm">
          "Tell me about a time you used data to persuade stakeholders to change
          their decision."
        </p>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded-2xl border border-dashed border-white/20 p-4">
            <p className="text-xs uppercase tracking-wide text-white/50">
              Your answer
            </p>
            <p className="mt-2 text-xs text-white/40">
              Start typing or speaking your answer here…
            </p>
          </div>
          <div className="rounded-2xl bg-white/5 p-4">
            <p className="text-xs uppercase tracking-wide text-white/50">
              AI sample answer
            </p>
            <p className="mt-2 text-xs text-white/40">
              Uses your project and experience to personalize your story.
            </p>
          </div>
        </div>
        <div className="mt-5 flex items-center justify-between">
          <span className="rounded-full bg-white/10 px-4 py-2 text-xs">
            Next question
          </span>
          <span className="text-xs text-white/40">Q2 · Behavioral</span>
        </div>
      </div>
    </div>
  );
}
