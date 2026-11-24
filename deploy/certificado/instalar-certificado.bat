@echo off
rem Instala o certificado da autoridade certificadora interna (CA) da empresa.
rem Depois disso o navegador confia em https://ticket.internal e para de mostrar "Nao seguro".
rem Coloque este arquivo e o ca-empresa.crt na mesma pasta (ex.: F:\publico\certificado).
setlocal
set "CERT=%~dp0ca-empresa.crt"
if not exist "%CERT%" (
  echo Arquivo ca-empresa.crt nao encontrado ao lado deste script. Avise a T.I.
  pause
  exit /b 1
)
net session >nul 2>&1
if %errorlevel%==0 (
  echo Instalando para todos os usuarios deste computador...
  certutil -addstore -f Root "%CERT%"
) else (
  echo Instalando para o seu usuario.
  echo Se aparecer um "Aviso de Seguranca" perguntando se deseja instalar, clique em SIM.
  certutil -user -addstore -f Root "%CERT%"
)
if errorlevel 1 (
  echo.
  echo Nao foi possivel instalar o certificado. Avise a T.I.
) else (
  echo.
  echo Pronto! Feche o navegador, abra de novo e acesse https://ticket.internal
)
pause
