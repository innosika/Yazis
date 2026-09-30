import { ruCommon } from "./ru-common";
import { ruCorpus } from "./ru-corpus";
import { ruEval } from "./ru-eval";
import { ruLabHelp } from "./ru-lab-help";
import { ruSearch } from "./ru-search";

export const ru: Record<string, string> = { ...ruCommon, ...ruSearch, ...ruCorpus, ...ruEval, ...ruLabHelp };
