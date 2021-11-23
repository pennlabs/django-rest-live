// import dedent from 'ts-dedent';
import { Construct } from "constructs";
import { App, Stack } from "cdkactions";
import {PyPIPublishStack} from "@pennlabs/kraken";

export class MyStack extends Stack {
  constructor(scope: Construct, name: string) {
    super(scope, name);

    // define workflows here

  }
}

const app = new App();
new PyPIPublishStack(app)
app.synth();
