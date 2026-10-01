import { createOpenApiHttp } from 'openapi-msw'
import { setupServer } from 'msw/node'
import { createApi } from '../api/client'
import type { paths } from '../api/schema'

// The backend, as far as a test needs one. Handlers are typed from the same
// schema as the client (src/api/schema.d.ts): a path, a body or a response
// the API does not have is a compile error here too, so the fakes cannot
// drift from the real thing unnoticed. Each test registers what it needs with
// `server.use(...)`; anything else is an unhandled request and fails it.
export const API_URL = 'http://api.test'

export const http = createOpenApiHttp<paths>({ baseUrl: API_URL })

export const server = setupServer()

export const testApi = () => createApi(API_URL)
