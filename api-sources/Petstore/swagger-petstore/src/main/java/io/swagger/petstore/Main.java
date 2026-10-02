//MODIFIED: This code is a simple Java application that starts an embedded Tomcat server to serve the Swagger Petstore application.

package io.swagger.petstore;

import org.apache.catalina.Context;
import org.apache.catalina.Wrapper;
import org.apache.catalina.startup.Tomcat;
import org.apache.catalina.webresources.DirResourceSet;
import org.apache.catalina.webresources.JarResourceSet;
import org.apache.catalina.webresources.StandardRoot;

import javax.servlet.Servlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.file.Files;
import java.security.CodeSource;

public class Main {
    Tomcat tomcat;

    public void startServer(int port) throws Exception {
        tomcat = new Tomcat();

        String tmpDir = System.getProperty("java.io.tmpdir");
        tomcat.setBaseDir(tmpDir);

        tomcat.setPort(port);
        tomcat.getConnector();

        Context ctx = tomcat.addContext("", null);

        StandardRoot resources = new StandardRoot(ctx);
        CodeSource src = Main.class.getProtectionDomain().getCodeSource();
        if (src != null) {
            URL jar = src.getLocation();
            String jarPath = new File(jar.toURI()).getAbsolutePath();
            if (jarPath.endsWith(".jar")) {
                resources.addJarResources(new JarResourceSet(resources, "/", jarPath, "/webapp"));
            }else {
                URL webappUrl = Main.class.getClassLoader().getResource("webapp");
               String webappDirLocation = new File(webappUrl.toURI()).getAbsolutePath();
                resources.addPreResources(new DirResourceSet(resources, "/", webappDirLocation, "/"));
            }
        }
        ctx.setResources(resources);
        ctx.addWelcomeFile("index.html");

        // Swagger-Inflector / Jersey servlet
        Wrapper jerseyServlet = Tomcat.addServlet(ctx, "jersey-container-servlet",
                "org.glassfish.jersey.servlet.ServletContainer");

        jerseyServlet.addInitParameter("javax.ws.rs.Application", "io.swagger.oas.inflector.OpenAPIInflector");
        jerseyServlet.setLoadOnStartup(1);

        ctx.addServletMappingDecoded("/api/*", "jersey-container-servlet");

        Wrapper defaultServlet = Tomcat.addServlet(ctx, "default", "org.apache.catalina.servlets.DefaultServlet");
        defaultServlet.setLoadOnStartup(1);
        ctx.addServletMappingDecoded("/", "default");

        System.out.println("Swagger Petstore running at http://localhost:" + port);
        tomcat.start();
    }

    public Tomcat getTomcat() {
        return tomcat;
    }


    public static void main(String[] args) throws Exception {
        int port = 8080;

        if (args.length > 0) {
            try {
                port = Integer.parseInt(args[0]);
            } catch (NumberFormatException e) {
                System.err.println("Invalid port number: " + args[0] + ". Using default port 8080.");
            }
        }

        Main app = new Main();
        app.startServer(port);

    }
}