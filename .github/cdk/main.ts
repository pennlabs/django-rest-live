// import dedent from 'ts-dedent';
import { App } from "cdkactions";
import { PyPIPublishStack } from "@pennlabs/kraken";

const app = new App();
new PyPIPublishStack(app, {
  pythonMatrixVersions: [3.7, 3.8, 3.9]
});

app.synth();
