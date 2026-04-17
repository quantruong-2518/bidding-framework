import {
  BadRequestException,
  Controller,
  Logger,
  MaxFileSizeValidator,
  ParseFilePipe,
  Post,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { Roles } from '../auth/roles.decorator';
import { ParseResponse, ParsersService } from './parsers.service';

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

@Controller('bids')
export class ParsersController {
  private readonly logger = new Logger(ParsersController.name);

  constructor(private readonly parsers: ParsersService) {}

  @Post('parse-rfp')
  @Roles('admin', 'bid_manager')
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: MAX_UPLOAD_BYTES } }))
  async parseRfp(
    @UploadedFile(
      new ParseFilePipe({
        validators: [new MaxFileSizeValidator({ maxSize: MAX_UPLOAD_BYTES })],
      }),
    )
    file: Express.Multer.File | undefined,
  ): Promise<ParseResponse> {
    if (!file) {
      throw new BadRequestException('Missing multipart "file" field.');
    }
    this.logger.log(
      `parse_rfp.received file=${file.originalname} size=${file.size} mime=${file.mimetype}`,
    );
    return this.parsers.parseRfp(file.originalname, file.mimetype, file.buffer);
  }
}
