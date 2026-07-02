{{/*
Expand the name of the chart.
*/}}
{{- define "nsi-orchestrator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "nsi-orchestrator.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "nsi-orchestrator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "nsi-orchestrator.labels" -}}
helm.sh/chart: {{ include "nsi-orchestrator.chart" . }}
{{ include "nsi-orchestrator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "nsi-orchestrator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nsi-orchestrator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
envFrom (config + secret) and the CACHE_URI env for the scheduler containers.
*/}}
{{- define "nsi-orchestrator.schedulerEnv" -}}
envFrom:
{{- if .Values.secretProviderClass.enabled }}
  - secretRef:
      name: {{ .Release.Name }}-secret
{{- end }}
{{- if .Values.env }}
  - configMapRef:
      name: {{ .Release.Name }}-environment
{{- end }}
{{- if .Values.redis.enabled }}
env:
  - name: CACHE_URI
    value: "redis://{{ include "nsi-orchestrator.fullname" . }}-redis:6379/0"
{{- end }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "nsi-orchestrator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "nsi-orchestrator.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
