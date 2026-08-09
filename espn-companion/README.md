# Draft Tool ESPN Companion

This lightweight Chrome, Edge, and Firefox companion mirrors completed picks from the visible ESPN fantasy football draft room into Private Draft Tools.

## Download

Download the repository as a ZIP, unzip it, and locate the **espn-companion** folder.

## Install in Chrome or Edge

1. In Chrome, open **chrome://extensions**. In Edge, open **edge://extensions**.
2. Turn on **Developer mode**.
3. Choose **Load unpacked** and select the **espn-companion** folder.
4. Refresh Private Draft Tools and the ESPN draft-room tab.

Chrome or Edge 121 or newer is required.

## Install in Firefox

1. Open **about:debugging#/runtime/this-firefox**.
2. Select **Load Temporary Add-on**.
3. Open the **espn-companion** folder and select **manifest.json**.
4. Refresh Private Draft Tools and the ESPN draft-room tab.

Firefox 142 or newer is required. Firefox removes temporary add-ons when the browser closes, so repeat these steps after restarting Firefox. A permanently installed Firefox version would require Mozilla signing.

## Use during a draft

1. Open Private Draft Tools and your ESPN draft room in the same browser.
2. In Private Draft Tools, open **Settings**.
3. Choose **ESPN desktop browser** under **Live Draft Sync**.
4. Click **Check Connection**.

You should see a small **Draft Tool: watching ESPN** badge in the lower-right corner of the ESPN page. Leave both tabs open during the draft.

## Privacy

The companion reads only the visible ESPN fantasy pages matched in the extension manifest. It does not ask for, read, or transmit your ESPN password. Draft picks are passed locally between your ESPN tab and the Private Draft Tools tab.

## Troubleshooting

- Refresh both tabs after first installing or updating the companion.
- Confirm the lower-right companion badge appears in ESPN.
- Keep ESPN's draft board or recent-picks area visible.
- In Firefox, confirm the companion still appears under **Temporary Extensions** after a restart.
- If ESPN changes its draft-room layout, use Private Draft Tools' manual **Mark Drafted** control until the companion parser is updated.

ESPN mobile is not supported by the companion. Manual draft entry remains available for ESPN mobile and every other platform.
