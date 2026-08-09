# Draft Tool ESPN Companion

This lightweight Chrome/Edge companion mirrors completed picks from the visible ESPN fantasy football draft room into Private Draft Tools.

## Install

1. Download this repository as a ZIP and unzip it.
2. In Chrome, open **chrome://extensions**. In Edge, open **edge://extensions**.
3. Turn on **Developer mode**.
4. Choose **Load unpacked** and select the **espn-companion** folder.
5. Open the Private Draft Tools site and your ESPN draft room in the same browser.
6. In Private Draft Tools, open Settings, choose **ESPN desktop browser**, and click **Check Connection**.

You should see a small **Draft Tool: watching ESPN** badge in the lower-right corner of the ESPN page. Leave both tabs open during the draft.

## Privacy

The companion reads only the visible ESPN fantasy pages matched in the extension manifest. It does not ask for, read, or transmit your ESPN password. Draft picks are passed locally between your ESPN tab and the Private Draft Tools tab.

## Troubleshooting

- Refresh both tabs after first installing or updating the companion.
- Confirm the lower-right companion badge appears in ESPN.
- Keep ESPN's draft board or recent-picks area visible.
- If ESPN changes its draft-room layout, use Private Draft Tools' manual **Mark Drafted** control until the companion parser is updated.

ESPN mobile is not supported by the companion. Manual draft entry remains available for ESPN mobile and every other platform.
