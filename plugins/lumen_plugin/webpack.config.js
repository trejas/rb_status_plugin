const path = require("path");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

module.exports = (env) => {
  return {
    entry: {
      main: ["./src/js/index.js", "./src/scss/index.scss"],
    },
    output: {
      filename: "[name].js",
      path: path.resolve(__dirname, "static"),
    },
    mode: env.production ? "production" : "development",
    module: {
      rules: [
        {
          test: /\.scss$/,
          use: [
            // fallback to style-loader in development
            !env.production ? "style-loader" : MiniCssExtractPlugin.loader,
            "css-loader",
            "sass-loader",
          ],
        },
        {
          test: /\.m?js$/,
          exclude: /(node_modules|bower_components)/,
          use: {
            loader: "babel-loader",
            options: {
              presets: ["@babel/preset-env"],
            },
          },
        },
      ],
    },
    plugins: [
      new MiniCssExtractPlugin({
        filename: "[name].css",
      }),
    ],
  };
};