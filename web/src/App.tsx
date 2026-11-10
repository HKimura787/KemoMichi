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
  const [openingProject, setOpeningProject] = useState(false);
  const [projectSession, setProjectSession] = useState(0);

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
  return (
    <>
      {project && (
        <div hidden={openingProject} style={{ height: "100%" }}>
          <Workspace key={`${project.path}:${projectSession}`} info={info} project={project} setProject={setProject}
                     active={!openingProject} onOpenProject={() => setOpeningProject(true)} />
        </div>
      )}
      {(!project || openingProject) && (
        <OpenScreen info={info} onCancel={project ? () => setOpeningProject(false) : undefined}
                    onOpened={(opened) => {
                      setProject(opened);
                      setProjectSession((session) => session + 1);
                      setOpeningProject(false);
                    }} />
      )}
    </>
  );
}
