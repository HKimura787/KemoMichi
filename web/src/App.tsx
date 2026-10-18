import { useEffect, useState } from "react";
import { api } from "./api";
import { OpenScreen } from "./components/OpenScreen";
import { Workspace } from "./components/Workspace";
import { useI18n } from "./i18n";
import type { Info, Project } from "./types";
import { useToast } from "./ui";

export function App() {
  const { lang } = useI18n();
  const toast = useToast();
  const [info, setInfo] = useState<Info | null>(null);
  const [project, setProject] = useState<Project | null>(null);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    api.info().then(async (i) => {
      setInfo(i);
      if (i.projectOpen) setProject(await api.project());
    }).catch(toast.error);
  }, [toast.error]);

  if (!info) return null;
  if (!project) return <OpenScreen info={info} onOpened={setProject} />;
  return (
    <Workspace key={project.path} info={info} project={project} setProject={setProject}
               onLeave={async () => {
                 try { await api.close(); } catch { /* already closed */ }
                 setProject(null);
               }} />
  );
}
