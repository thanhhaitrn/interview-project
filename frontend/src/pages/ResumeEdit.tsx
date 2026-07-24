import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ResumeDocument } from "../api/types";
import { Button, ErrorNote, Spinner } from "../components/ui";
import { TagInput } from "../components/TagInput";

type Item = Record<string, any>;

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v));
}

function sectionItems(doc: ResumeDocument, name: string): Item[] {
  return doc.sections.find((s) => s.section_name === name)?.items ?? [];
}

export function ResumeEdit() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<ResumeDocument | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState("");

  useEffect(() => {
    api
      .getResume(id)
      .then(setDoc)
      .catch((e) => setError((e as Error).message));
  }, [id]);

  if (error && !doc) return <ErrorNote message={error} />;
  if (!doc) return <Spinner label="Loading resume…" />;

  // --- mutation helpers operating on a deep clone ---
  function update(mutate: (d: ResumeDocument) => void) {
    setDoc((prev) => {
      const next = clone(prev!);
      mutate(next);
      return next;
    });
  }

  function setItems(name: string, items: Item[]) {
    update((d) => {
      const idx = d.sections.findIndex((s) => s.section_name === name);
      if (idx === -1) d.sections.push({ section_name: name, items });
      else d.sections[idx].items = items;
    });
  }

  const experience = sectionItems(doc, "Work Experience");
  const projects = sectionItems(doc, "Projects");
  const education = sectionItems(doc, "Education");
  const skills: string[] = sectionItems(doc, "Skills").flatMap(
    (i) => (i.bullets as string[]) ?? []
  );
  const courses: string[] = education.flatMap(
    (e) => (e.relevant_courses as string[]) ?? []
  );

  function patchItem(name: string, index: number, patch: Item) {
    const items = clone(sectionItems(doc!, name));
    items[index] = { ...items[index], ...patch };
    setItems(name, items);
  }

  function addBullet(name: string, index: number) {
    const items = clone(sectionItems(doc!, name));
    items[index].bullets = [...(items[index].bullets ?? []), ""];
    setItems(name, items);
  }

  function setBullet(name: string, index: number, bi: number, value: string) {
    const items = clone(sectionItems(doc!, name));
    items[index].bullets[bi] = value;
    setItems(name, items);
  }

  function removeBullet(name: string, index: number, bi: number) {
    const items = clone(sectionItems(doc!, name));
    items[index].bullets = items[index].bullets.filter((_: string, j: number) => j !== bi);
    setItems(name, items);
  }

  function removeItem(name: string, index: number) {
    setItems(name, sectionItems(doc!, name).filter((_, j) => j !== index));
  }

  function addExperience() {
    setItems("Work Experience", [
      ...experience,
      { job_title: "", company: "", location: "", start_date: "", end_date: "", bullets: [] },
    ]);
  }

  function addProject() {
    setItems("Projects", [...projects, { project_name: "", bullets: [] }]);
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      await api.saveResume(id, doc!);
      setSavedAt(new Date().toLocaleTimeString());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const input = "w-full rounded-xl border border-navy/15 px-3 py-2 text-sm";

  return (
    <div>
      <button
        onClick={() => navigate("/resume")}
        className="mb-3 text-sm text-navy/60 hover:text-navy"
      >
        ← Back to List
      </button>
      <div className="mb-6 flex items-center justify-between">
        <p className="text-navy/60">
          Adjust entries, bullets, and education. These ground the questions and
          feedback in your interview practice.
        </p>
        <div className="flex items-center gap-3">
          {savedAt && <span className="text-sm text-green-600">Saved {savedAt}</span>}
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>

      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="grid gap-8 lg:grid-cols-2">
        {/* LEFT: Experience & Projects */}
        <div>
          <h2 className="text-2xl font-bold">Experience & Projects</h2>

          <h3 className="mt-5 text-sm font-bold uppercase tracking-wide text-navy/60">
            Work Experience
          </h3>
          <div className="mt-3 space-y-5">
            {experience.map((it, i) => (
              <div key={i} className="card p-5">
                <div className="flex gap-2">
                  <input
                    className={input}
                    placeholder="Job title"
                    value={it.job_title ?? ""}
                    onChange={(e) => patchItem("Work Experience", i, { job_title: e.target.value })}
                  />
                  <input
                    className={input}
                    placeholder="Company"
                    value={it.company ?? ""}
                    onChange={(e) => patchItem("Work Experience", i, { company: e.target.value })}
                  />
                  <button
                    onClick={() => removeItem("Work Experience", i)}
                    className="shrink-0 px-2 text-navy/40 hover:text-rose-500"
                    title="Delete entry"
                  >
                    🗑
                  </button>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <input
                    className={input}
                    placeholder="Location (e.g., Boston, MA)"
                    value={it.location ?? ""}
                    onChange={(e) => patchItem("Work Experience", i, { location: e.target.value })}
                  />
                  <div className="flex gap-2">
                    <input
                      className={input}
                      placeholder="Start (YYYY-MM)"
                      value={it.start_date ?? ""}
                      onChange={(e) => patchItem("Work Experience", i, { start_date: e.target.value })}
                    />
                    <input
                      className={input}
                      placeholder="End (YYYY-MM)"
                      value={it.end_date ?? ""}
                      onChange={(e) => patchItem("Work Experience", i, { end_date: e.target.value })}
                    />
                  </div>
                </div>
                <BulletEditor
                  bullets={it.bullets ?? []}
                  onAdd={() => addBullet("Work Experience", i)}
                  onChange={(bi, v) => setBullet("Work Experience", i, bi, v)}
                  onRemove={(bi) => removeBullet("Work Experience", i, bi)}
                />
              </div>
            ))}
            <Button variant="subtle" onClick={addExperience}>
              + Add experience
            </Button>
          </div>

          <h3 className="mt-8 text-sm font-bold uppercase tracking-wide text-navy/60">
            Projects
          </h3>
          <div className="mt-3 space-y-5">
            {projects.map((it, i) => (
              <div key={i} className="card p-5">
                <div className="flex gap-2">
                  <input
                    className={input}
                    placeholder="Project name"
                    value={it.project_name ?? ""}
                    onChange={(e) => patchItem("Projects", i, { project_name: e.target.value })}
                  />
                  <button
                    onClick={() => removeItem("Projects", i)}
                    className="shrink-0 px-2 text-navy/40 hover:text-rose-500"
                    title="Delete project"
                  >
                    🗑
                  </button>
                </div>
                <BulletEditor
                  bullets={it.bullets ?? []}
                  onAdd={() => addBullet("Projects", i)}
                  onChange={(bi, v) => setBullet("Projects", i, bi, v)}
                  onRemove={(bi) => removeBullet("Projects", i, bi)}
                />
              </div>
            ))}
            <Button variant="subtle" onClick={addProject}>
              + Add project
            </Button>
          </div>
        </div>

        {/* RIGHT: Education & Profile */}
        <div>
          <h2 className="text-2xl font-bold">Education & Profile</h2>

          <h3 className="mt-5 text-sm font-bold uppercase tracking-wide text-navy/60">
            Education
          </h3>
          <div className="mt-3 space-y-4">
            {education.map((it, i) => (
              <div key={i} className="card space-y-2 p-5">
                <input
                  className={input}
                  placeholder="Institution"
                  value={it.institution ?? ""}
                  onChange={(e) => patchItem("Education", i, { institution: e.target.value })}
                />
                <div className="grid grid-cols-2 gap-2">
                  <input
                    className={input}
                    placeholder="Degree"
                    value={it.degree ?? ""}
                    onChange={(e) => patchItem("Education", i, { degree: e.target.value })}
                  />
                  <input
                    className={input}
                    placeholder="Field of study"
                    value={it.field_of_study ?? ""}
                    onChange={(e) => patchItem("Education", i, { field_of_study: e.target.value })}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <input
                    className={input}
                    placeholder="Start"
                    value={it.start_date ?? ""}
                    onChange={(e) => patchItem("Education", i, { start_date: e.target.value })}
                  />
                  <input
                    className={input}
                    placeholder="End"
                    value={it.end_date ?? ""}
                    onChange={(e) => patchItem("Education", i, { end_date: e.target.value })}
                  />
                  <input
                    className={input}
                    placeholder="GPA"
                    value={it.gpa ?? ""}
                    onChange={(e) => patchItem("Education", i, { gpa: e.target.value })}
                  />
                </div>
                <button
                  onClick={() => removeItem("Education", i)}
                  className="text-sm text-navy/40 hover:text-rose-500"
                >
                  Remove
                </button>
              </div>
            ))}
            <Button
              variant="subtle"
              onClick={() =>
                setItems("Education", [
                  ...education,
                  { institution: "", degree: "", field_of_study: "", relevant_courses: [] },
                ])
              }
            >
              + Add education
            </Button>
          </div>

          <h3 className="mt-8 text-sm font-bold uppercase tracking-wide text-navy/60">
            Skills
          </h3>
          <div className="mt-3 card p-5">
            <TagInput
              values={skills}
              placeholder="Add a skill and press Enter"
              onChange={(next) => setItems("Skills", [{ bullets: next }])}
            />
          </div>

          <h3 className="mt-8 text-sm font-bold uppercase tracking-wide text-navy/60">
            Courses
          </h3>
          <div className="mt-3 card p-5">
            <TagInput
              values={courses}
              placeholder="Add a course and press Enter"
              onChange={(next) => {
                const items = clone(education);
                if (items.length === 0)
                  items.push({ institution: "", relevant_courses: next });
                else items[0].relevant_courses = next;
                setItems("Education", items);
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function BulletEditor({
  bullets,
  onAdd,
  onChange,
  onRemove,
}: {
  bullets: string[];
  onAdd: () => void;
  onChange: (i: number, v: string) => void;
  onRemove: (i: number) => void;
}) {
  return (
    <div className="mt-3">
      <p className="text-xs font-medium uppercase tracking-wide text-navy/40">
        Bullets
      </p>
      <div className="mt-2 space-y-2">
        {bullets.map((b, bi) => (
          <div key={bi} className="flex items-start gap-2">
            <textarea
              value={b}
              onChange={(e) => onChange(bi, e.target.value)}
              rows={2}
              className="flex-1 rounded-xl border border-navy/15 px-3 py-2 text-sm"
            />
            <button
              onClick={() => onRemove(bi)}
              className="mt-1 px-2 text-navy/40 hover:text-rose-500"
              title="Remove bullet"
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <button
        onClick={onAdd}
        className="mt-2 rounded-full bg-navy/5 px-3 py-1 text-sm hover:bg-navy/10"
      >
        + Bullet
      </button>
    </div>
  );
}
