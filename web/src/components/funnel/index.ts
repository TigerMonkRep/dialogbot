/** The shared funnel kit (/start and /privat/start). See docs: the funnel brief. */
export { FunnelProvider, useFunnel, reachableStep, readGateInfo } from "./provider";
export { FunnelShell, Sim } from "./shell";
export { Question, Choice, NextButton, Estimate, FunnelState, type Option } from "./parts";
export { PlaceSearch } from "./place-search";
export { BuildProgress, type BuildRow, type RowState } from "./build-progress";
export { Gate, CodeStep, validPhone } from "./gate";
