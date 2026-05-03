{{/*
Expand the name of the chart.
*/}}
{{- define "content-autopilot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "content-autopilot.fullname" -}}
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
Common labels
*/}}
{{- define "content-autopilot.labels" -}}
helm.sh/chart: {{ include "content-autopilot.chart" . }}
{{ include "content-autopilot.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Chart label
*/}}
{{- define "content-autopilot.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "content-autopilot.selectorLabels" -}}
app.kubernetes.io/name: {{ include "content-autopilot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend image (also used for celery-worker and celery-beat)
*/}}
{{- define "content-autopilot.backendImage" -}}
{{- printf "%s/%s:%s" .Values.global.registry .Values.backend.image.repository .Values.global.imageTag }}
{{- end }}

{{/*
MCP Server image
*/}}
{{- define "content-autopilot.mcpServerImage" -}}
{{- printf "%s/%s:%s" .Values.global.registry .Values.mcpServer.image.repository .Values.global.imageTag }}
{{- end }}

{{/*
Nginx image
*/}}
{{- define "content-autopilot.nginxImage" -}}
{{- printf "%s/%s:%s" .Values.global.registry .Values.nginx.image.repository .Values.global.imageTag }}
{{- end }}
