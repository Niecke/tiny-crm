import type { components } from './schema'

// Short names for generated schemas that a screen names explicitly (a prop, a
// mutation body). Aliases only — the shapes come from the backend; never add
// fields here. Most code needs none: query results are typed by the call.
type Schemas = components['schemas']

export type OrganizationRead = Schemas['OrganizationRead']
export type OrganizationCreate = Schemas['OrganizationCreate']
export type BriefingRead = Schemas['BriefingRead']
export type BriefingTask = Schemas['BriefingTask']
export type BriefingInteraction = Schemas['BriefingInteraction']
export type CaptureRead = Schemas['CaptureRead']
export type CaptureStatus = Schemas['CaptureRead']['status']
export type CaptureConvert = Schemas['CaptureConvert']
export type ContactRead = Schemas['ContactRead']
export type ContactCreate = Schemas['ContactCreate']
export type TaskRead = Schemas['TaskRead']
export type TaskCreate = Schemas['TaskCreate']
export type TaskUpdate = Schemas['TaskUpdate']
export type InteractionRead = Schemas['InteractionRead']
export type InteractionCreate = Schemas['InteractionCreate']
export type DocumentRead = Schemas['DocumentRead']
export type DocumentUpdate = Schemas['DocumentUpdate']
export type DealRead = Schemas['DealRead']
export type DealCreate = Schemas['DealCreate']
export type DealUpdate = Schemas['DealUpdate']
export type ProjectRead = Schemas['ProjectRead']
export type ProjectCreate = Schemas['ProjectCreate']
export type ProjectUpdate = Schemas['ProjectUpdate']
export type WatchRead = Schemas['WatchRead']
export type WatchCreate = Schemas['WatchCreate']
export type WatchUpdate = Schemas['WatchUpdate']
export type WatchCheckCreate = Schemas['WatchCheckCreate']
