DIM objShell
set objShell=wscript.createObject("wscript.shell")
iReturn=objShell.Run("cmd.exe /C E:\MyGitHubProjct\UniquePaperFromGoogleScholarAlter\Uniquepaper.bat", 0, TRUE)