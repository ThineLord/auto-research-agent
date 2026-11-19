"""Download availability follows the selected project's latest recovery state."""

from playwright.sync_api import expect


def test_download_disables_after_recovery_blocks_output(dashboard):
    page = dashboard.page
    (dashboard.project / "best_output.md").write_text("Synthetic output")
    page.reload()
    page.locator('[data-nav="outputs"]').first.click()
    document = page.locator("#document")
    download = page.locator('[data-action="download"]')
    expect(document).to_contain_text("Synthetic output")
    expect(download).to_be_enabled()
    blocked = dashboard.project / ".round_commit_transaction.json"
    blocked.write_text("{not a journal")
    page.evaluate("""() => {
        const create = URL.createObjectURL;
        window.createdBlobs = [];
        URL.createObjectURL = blob => {
            window.createdBlobs.push(blob.size);
            return create.call(URL, blob);
        };
    }""")
    downloads = []
    page.on("download", lambda event: downloads.append(event))
    # The catalog still shows an available file when the download is requested.
    download.click()
    expect(document).to_contain_text("Round commit recovery is blocked.")
    expect(download).to_be_disabled()
    assert downloads == []
    assert page.evaluate("window.createdBlobs") == []

    # The preview request must also update both the message and the control.
    blocked.unlink()
    page.reload()
    expect(document).to_contain_text("Synthetic output")
    blocked.write_text("{not a journal")
    page.locator(".file-row").first.click()
    expect(document).to_contain_text("Round commit recovery is blocked.")
    expect(download).to_be_disabled()


def test_late_download_response_leaves_new_project_readable(dashboard):
    page = dashboard.page
    second = dashboard.workspace_root / "second"
    second.mkdir()
    (second / "task.md").write_text("Second synthetic project")
    (second / "best_output.md").write_text("Second output")
    (dashboard.project / "best_output.md").write_text("First output")
    page.reload()
    page.locator('[data-nav="outputs"]').first.click()
    document = page.locator("#document")
    download = page.locator('[data-action="download"]')
    expect(document).to_contain_text("First output")
    (dashboard.project / ".round_commit_transaction.json").write_text("{not a journal")

    # Hold the first project's actual JSON response until the second project is on screen.
    page.evaluate("""() => {
        const original = Response.prototype.json;
        Response.prototype.json = async function () {
            const value = await original.call(this);
            const url = new URL(this.url);
            if (url.pathname === "/api/output" && url.searchParams.get("project") === "example") {
                await new Promise(resolve => {
                    window.releaseDownload = resolve;
                    document.body.dataset.download = "waiting";
                });
                setTimeout(() => { document.body.dataset.download = "handled"; }, 0);
            }
            return value;
        };
    }""")
    download.click()
    expect(page.locator("body")).to_have_attribute("data-download", "waiting")
    page.locator("#project").select_option("second")
    expect(document).to_contain_text("Second output")
    page.evaluate("window.releaseDownload()")
    expect(page.locator("body")).to_have_attribute("data-download", "handled")
    expect(document).to_contain_text("Second output")
    expect(download).to_be_enabled()
