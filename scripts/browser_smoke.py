"""Real browser smoke test using an installed Edge, Chrome, or Playwright Chromium."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/browser"
OUT.mkdir(parents=True,exist_ok=True)
with socket.socket() as sock:
    sock.bind(("127.0.0.1",0))
    port=sock.getsockname()[1]
with TemporaryDirectory(prefix="folio-browser-") as folder:
    env={**os.environ,"FOLIO_DATA_DIR":folder}
    flags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
    with (OUT/"server.log").open("w") as logfile:
        server=subprocess.Popen([sys.executable,"-m","uvicorn","folio.api:app","--host","127.0.0.1","--port",str(port)],
                                cwd=ROOT,env=env,stdout=logfile,stderr=logfile,creationflags=flags)
        try:
            url=f"http://127.0.0.1:{port}"
            for _ in range(120):
                try:
                    if httpx.get(url+"/api/status",timeout=2).status_code==200:break
                except httpx.RequestError:pass
                time.sleep(.5)
            else:raise RuntimeError("Server did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="msedge",headless=True)
                page=browser.new_page(viewport={"width":1440,"height":1050},device_scale_factor=1)
                errors=[]
                page.on("pageerror",lambda e:errors.append(str(e)))
                page.goto(url)
                page.locator("#auth-toggle").click()
                page.locator("#auth-email").fill("browser-test@example.com")
                page.locator("#auth-password").fill("BrowserTest12345")
                page.locator("#auth-submit").click()
                page.locator("#doc-count").wait_for()
                page.locator("#upload").set_input_files([str(ROOT/"data/samples/passport.pdf"),str(ROOT/"data/samples/insurance.txt")])
                expect(page.locator("#doc-count")).to_have_text("2",timeout=30000)
                page.screenshot(path=str(OUT/"library-desktop.png"),full_page=True)
                page.get_by_role("button",name="passport.pdf",exact=False).click()
                page.locator("#detail").wait_for(state="visible")
                with page.expect_download() as download:
                    page.get_by_text("Download original document",exact=True).click()
                assert download.value.suggested_filename=="passport.pdf"
                page.locator("#ask-document").click()
                page.locator("#question").fill("When does my passport expire?")
                page.locator("#send").click()
                page.locator(".bubble.assistant").filter(has_text="2032-06-10").wait_for()
                assert page.locator(".source-card").count()>=1
                page.locator("#question").fill("give a brief note about this document")
                page.locator("#send").click()
                expect(page.locator(".bubble.assistant").last).to_contain_text("Brief overview")
                page.locator("#question").fill("hi")
                page.locator("#send").click()
                expect(page.locator(".bubble.assistant").last).to_contain_text("Hello!")
                page.route("**/api/chat", lambda route: route.abort("connectionrefused"))
                page.locator("#question").fill("When does my passport expire?")
                page.locator("#send").click()
                expect(page.locator(".bubble.assistant").last).to_contain_text("Cannot reach the local Folio server")
                expect(page.locator("#question")).to_have_value("When does my passport expire?")
                page.unroute("**/api/chat")
                page.locator("#send").click()
                expect(page.locator(".bubble.assistant").last).to_contain_text("2032-06-10")
                page.screenshot(path=str(OUT/"chat-desktop.png"),full_page=True)
                page.locator("#new-chat").click()
                expect(page.locator("#messages")).to_be_empty()
                page.locator(".history-item").first.click()
                expect(page.locator(".bubble.assistant").last).to_contain_text("2032-06-10")
                page.locator('[data-view="training"]').click()
                page.locator(".report").first.wait_for()
                page.screenshot(path=str(OUT/"model-lab.png"),full_page=True)
                page.set_viewport_size({"width":390,"height":844})
                page.locator('[data-view="library"]').click()
                page.screenshot(path=str(OUT/"library-mobile.png"),full_page=True)
                assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"),"Mobile horizontal overflow"
                assert not errors,errors
                browser.close()
            (OUT/"report.json").write_text(json.dumps({"passed":True,"checks":["upload","library","original download","document-scoped chat","source passages","signup","saved chat resume","overview","greeting","connection loss and retry","model lab","mobile layout"],"javascript_errors":errors},indent=2))
            print("Browser checks passed; screenshots saved in",OUT)
        finally:
            server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()
