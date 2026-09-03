{{- define "tinycrm.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tinycrm.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "tinycrm.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{ include "tinycrm.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "tinycrm.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tinycrm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Name of the CloudNativePG Cluster. The operator derives its Services from this,
so the read-write endpoint is <cluster>-rw — that is what DATABASE_URL points at.
*/}}
{{- define "tinycrm.postgresCluster" -}}
{{- printf "%s-postgres" (include "tinycrm.fullname" .) -}}
{{- end -}}

{{- define "tinycrm.postgresHost" -}}
{{- printf "%s-rw" (include "tinycrm.postgresCluster" .) -}}
{{- end -}}

{{/*
Used by both the backend Secret and the migration hook's own Secret. The two
cannot share one object: pre-upgrade hooks run before the release's regular
manifests are applied, so the backend Secret does not exist yet when the hook
starts.
*/}}
{{- define "tinycrm.databaseUrl" -}}
{{- printf "postgresql+asyncpg://%s:%s@%s:5432/%s" .Values.postgres.username .Values.postgres.password (include "tinycrm.postgresHost" .) .Values.postgres.database -}}
{{- end -}}

{{- define "tinycrm.minioFullname" -}}
{{- printf "%s-minio" (include "tinycrm.fullname" .) -}}
{{- end -}}

{{- define "tinycrm.minioEndpoint" -}}
{{- printf "http://%s:9000" (include "tinycrm.minioFullname" .) -}}
{{- end -}}
