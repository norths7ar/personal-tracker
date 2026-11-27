import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { NoteCompose } from "./note-compose";
import { NoteLibrary } from "./note-library";
import "./notes-page.css";

type NotesTab = "compose" | "library";

function parseTab(value: string | null): NotesTab {
  return value === "library" ? "library" : "compose";
}

export function NotesPage() {
  const [params, setParams] = useSearchParams();
  const activeTab = parseTab(params.get("tab"));
  const [selectedId, setSelectedId] = useState<number | null>(null);

  function selectTab(tab: NotesTab) {
    if (tab === activeTab) return;
    const next = new URLSearchParams(params);
    if (tab === "compose") next.delete("tab");
    else next.set("tab", tab);
    setParams(next);
  }

  return (
    <section className="page-stack notes-page">
      <header className="page-heading">
        <h1 className="page-title">日记</h1>
      </header>

      <div className="page-tabs notes-tabs" aria-label="日记视图">
        <button
          type="button"
          className={cn("page-tab", activeTab === "compose" && "page-tab-selected")}
          aria-pressed={activeTab === "compose"}
          onClick={() => selectTab("compose")}
        >
          记录
        </button>
        <button
          type="button"
          className={cn("page-tab", activeTab === "library" && "page-tab-selected")}
          aria-pressed={activeTab === "library"}
          onClick={() => selectTab("library")}
        >
          查看
        </button>
      </div>

      {activeTab === "compose" ? (
        <NoteCompose
          onSaved={(note) => setSelectedId(note.id)}
          onOpenLibrary={(id) => {
            setSelectedId(id);
            selectTab("library");
          }}
        />
      ) : (
        <NoteLibrary selected={selectedId} onSelect={setSelectedId} />
      )}
    </section>
  );
}
