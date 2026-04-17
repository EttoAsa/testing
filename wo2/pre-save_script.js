const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");

(async () => {
  const downloadPath = path.join(__dirname, "saved_files/");

  const browser = await puppeteer.launch({
    headless: true, // Set to false if you want to see the browser actions
    args: [
      "--disable-web-security",
      "--no-sandbox",
      "--disable-setuid-sandbox",
    ], // Disable web security for local file access
  });
  const page = await browser.newPage();

  await page.setViewport({
    width: 1920,
    height: 1080,
    deviceScaleFactor: 1,
  });

  const client = await page.createCDPSession();
  await client.send("Browser.setDownloadBehavior", {
    behavior: "allow",
    downloadPath,
    eventsEnabled: true
  });
  // Wait for the download to complete (adjust timeout as necessary)
  client.on("Browser.downloadProgress", (e) => {
  if (e.state === "completed") {
    console.log("\x1b[0;32mDownload complete!\x1b[0m");
  } else if (e.state === "canceled") {
    console.log("\x1b[0;31mDownload canceled!\x1b[0m");
  }
});


  // Adjust this path to the directory containing your HTML files
  const directoryPath = __dirname;

  fs.readdir(directoryPath, async (err, files) => {
    if (err) {
      return console.log("Unable to scan directory: " + err);
    }

    for (const file of files) {
      if (path.extname(file) === ".html") {
        console.log(`Processing file: ${file}...`);
        const filePath = path.join(directoryPath, file);
        const content = fs.readFileSync(filePath, "utf8");

        // Load the HTML content in Puppeteer
        await page.goto("file://" + filePath);

        // Wait for the switch to be available and turn it on
        await page.waitForSelector(".switch"); // Adjust selector for your switch
        await page.click(".switch"); // Simulate turning the switch on

        // Wait for CKEditor5 to initialize
        await page.waitForSelector(".ck-editor__editable");

        // Trigger the save/download button
        await page.waitForSelector("#download_btn"); // Adjust selector for your save button
        await page.click("#download_btn"); // Simulate clicking the save button

        
        console.log(`Processed and triggered download for: ${file}`);
      }
    }

    await browser.close();
  });
})();
