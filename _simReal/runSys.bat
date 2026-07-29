@echo off
chcp 65001 > nul
title SimReal System Master Orchestrator

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0runSys.ps1"
