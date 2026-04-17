import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { UnsupportedMediaTypeException } from '@nestjs/common';
import { Test, type TestingModule } from '@nestjs/testing';
import { of, throwError } from 'rxjs';
import type { AxiosError, AxiosResponse } from 'axios';
import { ParsersController } from '../src/parsers/parsers.controller';
import { ParsersService, type ParseResponse } from '../src/parsers/parsers.service';

describe('ParsersController', () => {
  let controller: ParsersController;
  let http: { post: jest.Mock };

  const okResponse = <T>(data: T): AxiosResponse<T> => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config: {} as any,
  });

  const sampleResponse: ParseResponse = {
    parsed_rfp: {
      source_format: 'pdf',
      source_filename: 'acme.pdf',
      page_count: 4,
      sections: [],
      tables: [],
      raw_text: '',
      metadata: {},
    },
    suggested_bid_card: {
      client_name: 'Acme Bank',
      industry: 'banking',
      region: 'APAC',
      requirement_candidates: ['shall expose REST API'],
      technology_keywords: ['rest'],
      estimated_profile_hint: 'M',
      confidence: 0.6,
    },
  };

  const pdfFile = (
    overrides: Partial<Express.Multer.File> = {},
  ): Express.Multer.File => ({
    fieldname: 'file',
    originalname: 'acme.pdf',
    encoding: '7bit',
    mimetype: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4 fake pdf body'),
    size: 22,
    destination: '',
    filename: '',
    path: '',
    stream: null as unknown as Express.Multer.File['stream'],
    ...overrides,
  });

  beforeEach(async () => {
    http = { post: jest.fn() };

    const moduleRef: TestingModule = await Test.createTestingModule({
      controllers: [ParsersController],
      providers: [
        ParsersService,
        { provide: HttpService, useValue: http },
        { provide: ConfigService, useValue: { get: () => 'http://ai-service:8001' } },
      ],
    }).compile();

    controller = moduleRef.get(ParsersController);
  });

  it('proxies a PDF upload to ai-service and returns the ParseResponse', async () => {
    http.post.mockReturnValueOnce(of(okResponse(sampleResponse)));

    const result = await controller.parseRfp(pdfFile());

    expect(result).toEqual(sampleResponse);
    expect(http.post).toHaveBeenCalledWith(
      'http://ai-service:8001/workflows/bid/parse-rfp',
      expect.any(FormData),
      expect.objectContaining({ timeout: expect.any(Number) }),
    );
  });

  it('rejects unsupported file extensions with 415', async () => {
    await expect(
      controller.parseRfp(
        pdfFile({ originalname: 'notes.txt', mimetype: 'text/plain' }),
      ),
    ).rejects.toBeInstanceOf(UnsupportedMediaTypeException);
    expect(http.post).not.toHaveBeenCalled();
  });

  it('maps ai-service 4xx errors to matching gateway exceptions', async () => {
    const upstreamErr: Partial<AxiosError> = {
      isAxiosError: true,
      response: {
        status: 400,
        statusText: 'Bad Request',
        data: { detail: 'Uploaded file is empty.' },
        headers: {},
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        config: {} as any,
      },
    };
    http.post.mockReturnValueOnce(throwError(() => upstreamErr));

    await expect(controller.parseRfp(pdfFile())).rejects.toMatchObject({
      status: 400,
      message: 'Uploaded file is empty.',
    });
  });
});
