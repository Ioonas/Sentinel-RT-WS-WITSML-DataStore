#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ejecuta la suite oficial wPCTT sin la interfaz gráfica.

La herramienta oficial ``wcat.exe`` es una GUI (PySide/Python 2.7), pero su
motor de pruebas (``wtl``) es el mismo que usan los scripts oficiales. Este
runner carga ese motor con las mismas variables de ``server/default_server.py``
y ``wtl_cfg.py``, establece la sesión WITSML y ejecuta ``scripts/testsuite.py``
tal cual se distribuye. No modifica scripts, WSDL ni XSD oficiales.

Uso (Python 2.7, desde cualquier directorio)::

    python run_wpctt.py <ruta_wPCTT> [script]

``script`` por defecto es ``testsuite``. Los artefactos quedan en
``<ruta_wPCTT>/results`` (log de sesión, log SOAP y ``witsml_result.txt``).
"""

from __future__ import print_function

import os
import sys


def main(argv):
    if len(argv) < 2:
        print("uso: run_wpctt.py <ruta_wPCTT> [script]")
        return 2

    tool_home = os.path.abspath(argv[1])
    script = argv[2] if len(argv) > 2 else "testsuite"
    if not os.path.isdir(os.path.join(tool_home, "scripts")):
        print("No se encontró scripts/ en %s" % tool_home)
        return 2

    os.chdir(tool_home)
    sys.path.insert(0, os.path.join(tool_home, "python27.zip"))
    sys.path.insert(0, tool_home)
    # Sin argumentos: se replica el comportamiento de wcat.exe (auto_start
    # desactivado en wtl_cfg.py); la sesión se inicia explícitamente abajo.
    sys.argv = ["wcat"]

    import wtl.config
    import wtl.results
    import wtl.script
    import wtl.store_prim
    import wtl.testlog
    import wtl.witsml

    if not wtl.store_prim.WITSMLServer.start_server_session():
        print("No se pudo iniciar la sesión WITSML")
        wtl.testlog.end_log_file()
        return 3

    try:
        wtl.witsml.run(script)
    finally:
        # ``testsuite.py`` llama a produce_and_reset_results(), que reinicia
        # los contadores; el total fiable es el del informe generado.
        failed = _report_failures()
        if failed is None:
            failed = wtl.script.Script.fail_number
        passed = wtl.script.Script.pass_number
        skipped = wtl.script.Script.skip_number
        wtl.testlog.end_log_file()
        print(
            "wPCTT %s: pass=%d fail=%d skip=%d"
            % (script, passed, failed, skipped)
        )

    return 1 if failed else 0


def _report_failures():
    import wtl.config

    result_file = os.path.join(wtl.config.result_directory, wtl.config.result_filename)
    if not os.path.isfile(result_file):
        return None
    for line in open(result_file):
        parts = line.split()
        if len(parts) == 2 and parts[0] == "Fail":
            return int(parts[1])
    return None


if __name__ == "__main__":
    sys.exit(main(sys.argv))
