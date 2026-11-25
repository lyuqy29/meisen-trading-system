' ============================================================
'  liuliu dashboard -- silent launcher used by the logon task
'  Runs start-hidden.cmd with no console window (style 0).
' ============================================================
Option Explicit
Dim sh, fso, here, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
cmd = "cmd.exe /c """ & here & "\start-hidden.cmd"""
sh.Run cmd, 0, False
